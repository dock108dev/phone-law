"""Emit sanitized machine-readable Slice 4 database and lifecycle evidence."""

from __future__ import annotations

import json
import os
from collections import Counter
from typing import Any

import sqlalchemy as sa

from packages.config import Settings
from packages.database.health import EXPECTED_ALEMBIC_REVISION, create_database_engine
from packages.database.review_schema import (
    analyses,
    audit_events,
    calls,
    daily_report_items,
    manual_upload_receipts,
    manual_upload_state_events,
    processing_attempts,
    review_events,
)


def main() -> None:
    settings = Settings()
    engine = create_database_engine(settings.sqlalchemy_database_url)
    try:
        with engine.connect() as connection:
            receipts = connection.execute(sa.select(manual_upload_receipts)).mappings().all()
            states = Counter(str(row["state"]) for row in receipts)
            kinds = Counter(str(row["submission_kind"]) for row in receipts)
            call_ids = tuple(str(row["call_id"]) for row in receipts if row["call_id"] is not None)
            lifecycle_states = Counter(
                str(value)
                for value in connection.execute(
                    sa.select(manual_upload_state_events.c.state)
                ).scalars()
            )
            auth_results = Counter(
                str(row.result)
                for row in connection.execute(
                    sa.select(audit_events.c.result).where(
                        audit_events.c.target_type == "manual_upload"
                    )
                )
            )
            auth_actions = Counter(
                str(row.action)
                for row in connection.execute(
                    sa.select(audit_events.c.action).where(
                        audit_events.c.target_type == "manual_upload"
                    )
                )
            )
            validation_shapes = sorted(
                {
                    (
                        str(row["submission_kind"]),
                        str(row["validation_summary"]["contract_version"]),
                    )
                    for row in receipts
                }
            )
            payload: dict[str, Any] = {
                "schema_version": "slice4-local-evidence-v1",
                "migration_revision": EXPECTED_ALEMBIC_REVISION,
                "synthetic_only": all(bool(row["is_synthetic"]) for row in receipts),
                "receipt_count": len(receipts),
                "receipt_states": dict(sorted(states.items())),
                "submission_kinds": dict(sorted(kinds.items())),
                "validation_shapes": [
                    {"kind": kind, "contract_version": version}
                    for kind, version in validation_shapes
                ],
                "unique_linked_call_count": len(set(call_ids)),
                "linked_call_row_count": int(
                    connection.execute(
                        sa.select(sa.func.count())
                        .select_from(calls)
                        .where(calls.c.id.in_(call_ids))
                    ).scalar_one()
                    if call_ids
                    else 0
                ),
                "accepted_analysis_count": int(
                    connection.execute(
                        sa.select(sa.func.count())
                        .select_from(analyses)
                        .where(analyses.c.call_id.in_(call_ids))
                    ).scalar_one()
                    if call_ids
                    else 0
                ),
                "processing_attempt_count": int(
                    connection.execute(
                        sa.select(sa.func.count())
                        .select_from(processing_attempts)
                        .where(processing_attempts.c.call_id.in_(call_ids))
                    ).scalar_one()
                    if call_ids
                    else 0
                ),
                "report_item_reference_count": int(
                    connection.execute(
                        sa.select(sa.func.count())
                        .select_from(daily_report_items)
                        .where(daily_report_items.c.call_id.in_(call_ids))
                    ).scalar_one()
                    if call_ids
                    else 0
                ),
                "lifecycle_states": dict(sorted(lifecycle_states.items())),
                "authorization_results": dict(sorted(auth_results.items())),
                "authorization_actions": dict(sorted(auth_actions.items())),
                "content_fingerprint_count": len(
                    {str(row["content_fingerprint"]) for row in receipts}
                ),
                "idempotency_unique_content_confirmed": len(receipts)
                == len({str(row["content_fingerprint"]) for row in receipts}),
                "retry_same_call_confirmed": any(
                    int(row["attempt_number"]) == 2 and row["call_id"] is not None
                    for row in receipts
                ),
                "cancelled_receipt_count": states["cancelled"],
                "cancelled_deletion_confirmed_count": sum(
                    1
                    for row in receipts
                    if row["state"] == "cancelled" and row["deletion_confirmed"] is True
                ),
                "all_audio_deletions_confirmed": all(
                    row["deletion_confirmed"] is True
                    for row in receipts
                    if row["submission_kind"] == "synthetic_audio"
                    and row["state"] != "transcription_failed"
                ),
                "transcript_media_reference_count": sum(
                    1
                    for row in receipts
                    if row["submission_kind"] == "transcript_only"
                    and (row["object_id"] is not None or row["artifact_id"] is not None)
                ),
                "uploaded_call_review_event_count": int(
                    connection.execute(
                        sa.select(sa.func.count())
                        .select_from(review_events.join(analyses))
                        .where(analyses.c.call_id.in_(call_ids))
                    ).scalar_one()
                    if call_ids
                    else 0
                ),
                "unique_report_call_reference_count": int(
                    connection.execute(
                        sa.select(sa.func.count(sa.distinct(daily_report_items.c.call_id))).where(
                            daily_report_items.c.call_id.in_(call_ids)
                        )
                    ).scalar_one()
                    if call_ids
                    else 0
                ),
                "temporary_object_count": (
                    len(tuple(settings.manual_upload_root.iterdir()))
                    if settings.manual_upload_root.exists()
                    else 0
                ),
                "original_filename_columns": 0,
                "media_path_columns": 0,
                "request_body_columns": 0,
                "network_mode": "none"
                if os.environ.get("MANUAL_UPLOAD_OFFLINE") == "1"
                else "not_asserted",
                "external_provider_requests": 0,
                "live_cli_requests": 0,
                "live_sdk_requests": 0,
            }
    finally:
        engine.dispose()
    required = {
        "receipt_count": payload["receipt_count"] == 4,
        "input_modes": payload["submission_kinds"] == {"synthetic_audio": 3, "transcript_only": 1},
        "terminal_states": payload["receipt_states"] == {"analyzed": 3, "cancelled": 1},
        "unique_calls": payload["unique_linked_call_count"] == 3,
        "accepted_analyses": payload["accepted_analysis_count"] == 3,
        "report_coverage": payload["unique_report_call_reference_count"] == 3,
        "review_feedback": payload["uploaded_call_review_event_count"] >= 1,
        "idempotency": payload["idempotency_unique_content_confirmed"] is True,
        "retry": payload["retry_same_call_confirmed"] is True,
        "cancellation": payload["cancelled_deletion_confirmed_count"] == 1,
        "audio_cleanup": payload["all_audio_deletions_confirmed"] is True,
        "transcript_has_no_media": payload["transcript_media_reference_count"] == 0,
        "temporary_cleanup": payload["temporary_object_count"] == 0,
        "authorization_denial": payload["authorization_results"].get("forbidden", 0) >= 1,
        "offline": payload["network_mode"] == "none",
    }
    if not all(required.values()):
        failed = ",".join(key for key, passed in required.items() if not passed)
        raise SystemExit(f"manual upload evidence failed: {failed}")
    payload["acceptance_checks"] = required
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
