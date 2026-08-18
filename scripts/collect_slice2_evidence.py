"""Emit content-free database evidence for the disposable Slice 2 browser run."""

from __future__ import annotations

import hashlib
import json

import sqlalchemy as sa

from packages.config import Settings
from packages.database.health import create_database_engine
from packages.database.review_schema import (
    analyses,
    audit_events,
    calls,
    daily_report_items,
    daily_reports,
    ingestion_events,
    playbook_versions,
    processing_attempts,
    review_events,
)


def digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def main() -> None:
    settings = Settings(service_name="slice2-evidence")
    if not settings.synthetic_mode:
        raise SystemExit("Slice 2 evidence collection is synthetic-only")
    engine = create_database_engine(settings.sqlalchemy_database_url)
    try:
        with engine.connect() as connection:
            migration = connection.execute(
                sa.text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            report_row = connection.execute(
                sa.select(
                    daily_reports.c.business_date,
                    daily_reports.c.version,
                    daily_reports.c.status,
                    daily_reports.c.snapshot_payload,
                ).order_by(daily_reports.c.business_date.desc(), daily_reports.c.version.desc())
            ).first()
            assert report_row is not None
            section_counts = {
                section: int(count)
                for section, count in connection.execute(
                    sa.select(daily_report_items.c.section, sa.func.count())
                    .group_by(daily_report_items.c.section)
                    .order_by(daily_report_items.c.section)
                )
            }
            review_summary = [
                {
                    "label": label,
                    "principal_id": principal_id,
                    "role": role,
                    "note_present": note is not None,
                }
                for label, principal_id, role, note in connection.execute(
                    sa.select(
                        review_events.c.label,
                        review_events.c.principal_id,
                        review_events.c.role,
                        review_events.c.note,
                    ).order_by(review_events.c.created_at)
                )
            ]
            audit_summary = [
                {"action": action, "result": result, "principal_id": principal_id}
                for action, result, principal_id in connection.execute(
                    sa.select(
                        audit_events.c.action,
                        audit_events.c.result,
                        audit_events.c.principal_id,
                    ).order_by(audit_events.c.created_at)
                )
            ]
            call_002 = connection.execute(
                sa.select(calls.c.id).where(calls.c.fixture_id == "CL-FX-002")
            ).scalar_one()
            duplicate_underlying = connection.execute(
                sa.select(sa.func.count(sa.distinct(ingestion_events.c.call_id))).where(
                    ingestion_events.c.fixture_id.in_(["CL-FX-002", "CL-FX-009"])
                )
            ).scalar_one()
            analysis = connection.execute(
                sa.select(
                    analyses.c.original_payload,
                    analyses.c.playbook_version,
                    analyses.c.schema_version,
                    analyses.c.prompt_version,
                ).where(analyses.c.call_id == call_002)
            ).one()
            attempts = [
                {
                    "fixture_id": fixture_id,
                    "attempt_number": int(attempt_number),
                    "state": state,
                    "retryable": retryable,
                }
                for fixture_id, attempt_number, state, retryable in connection.execute(
                    sa.select(
                        calls.c.fixture_id,
                        processing_attempts.c.attempt_number,
                        processing_attempts.c.state,
                        processing_attempts.c.retryable,
                    )
                    .join(calls, calls.c.id == processing_attempts.c.call_id)
                    .where(calls.c.fixture_id.in_(["CL-FX-010", "CL-FX-011"]))
                    .order_by(calls.c.fixture_id, processing_attempts.c.attempt_number)
                )
            ]
            playbook = connection.execute(
                sa.select(
                    playbook_versions.c.version,
                    playbook_versions.c.status,
                    playbook_versions.c.structured_payload,
                    playbook_versions.c.published_at,
                ).where(playbook_versions.c.version == "synthetic-draft-v1")
            ).one()
            counts = {
                "reports": int(
                    connection.execute(
                        sa.select(sa.func.count()).select_from(daily_reports)
                    ).scalar_one()
                ),
                "report_items": int(
                    connection.execute(
                        sa.select(sa.func.count()).select_from(daily_report_items)
                    ).scalar_one()
                ),
                "review_events": int(
                    connection.execute(
                        sa.select(sa.func.count()).select_from(review_events)
                    ).scalar_one()
                ),
                "audit_events": int(
                    connection.execute(
                        sa.select(sa.func.count()).select_from(audit_events)
                    ).scalar_one()
                ),
            }
        output = {
            "synthetic": True,
            "migration_revision": migration,
            "report": {
                "business_date": str(report_row.business_date),
                "version": int(report_row.version),
                "status": report_row.status,
                "snapshot_sha256": digest(report_row.snapshot_payload),
                "section_counts": section_counts,
            },
            "counts": counts,
            "duplicate_source_call": {
                "fixture_references": ["CL-FX-002", "CL-FX-009"],
                "underlying_call_rows": int(duplicate_underlying),
            },
            "original_analysis_after_feedback": {
                "fixture_reference": "CL-FX-002",
                "payload_sha256": digest(analysis.original_payload),
                "playbook_version": analysis.playbook_version,
                "schema_version": analysis.schema_version,
                "prompt_version": analysis.prompt_version,
            },
            "review_events": review_summary,
            "audit_events": audit_summary,
            "failure_attempts": attempts,
            "playbook": {
                "version": playbook.version,
                "status": playbook.status,
                "published": playbook.published_at is not None,
                "structured_payload_sha256": digest(playbook.structured_payload),
            },
        }
        print(json.dumps(output, indent=2, sort_keys=True))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
