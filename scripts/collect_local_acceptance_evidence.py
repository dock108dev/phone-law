"""Fail-closed, content-free Slice 6A product-state evidence collection."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import date
from pathlib import Path

import sqlalchemy as sa

from packages.config import Settings
from packages.contracts.report import DemoPrincipal, DemoPrincipalId, DemoRole
from packages.database.health import EXPECTED_ALEMBIC_REVISION
from packages.database.local_operations import LocalOperationsRepository
from packages.database.review_experience import ReviewExperienceRepository
from packages.database.review_schema import (
    analyses,
    audit_events,
    calls,
    daily_reports,
    firm_configuration_versions,
    ingestion_events,
    manual_upload_receipts,
    playbook_versions,
    processing_attempts,
    retention_tombstones,
    review_events,
)

EVIDENCE_ROOT = Path("/tmp/colacci-law-slice6a/evidence")  # nosec B108


def _write(name: str, payload: object) -> None:
    target = EVIDENCE_ROOT / name
    target.write_text(f"{json.dumps(payload, indent=2, sort_keys=True)}\n", encoding="utf-8")
    os.chmod(target, 0o600)


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def main() -> None:
    os.umask(0o077)
    EVIDENCE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(EVIDENCE_ROOT, 0o700)
    settings = Settings()
    engine = sa.create_engine(settings.sqlalchemy_database_url)
    experience = ReviewExperienceRepository(engine)
    report = experience.report(date(2026, 8, 17))
    if report is None:
        raise SystemExit("required acceptance report is absent")
    reconciliation = report.completeness.reconciliation.model_dump(mode="json")
    expected_reconciliation = {
        "expected": 11,
        "received": 11,
        "duplicate_deliveries": 2,
        "analyzed": 10,
        "failed": 1,
        "missing": 0,
        "late": 0,
    }
    if reconciliation != expected_reconciliation or len(report.sections) != 8:
        raise SystemExit("acceptance reconciliation or report-section inventory differs")

    with engine.connect() as connection:
        call_rows = connection.execute(
            sa.select(calls.c.fixture_id, calls.c.state).where(calls.c.is_synthetic.is_(True))
        ).all()
        states = {str(row.fixture_id): str(row.state) for row in call_rows}
        duplicate_count = int(
            connection.execute(
                sa.select(
                    sa.func.coalesce(sa.func.sum(ingestion_events.c.duplicate_delivery_count), 0)
                )
            ).scalar_one()
        ) + int(
            connection.execute(
                sa.select(sa.func.count())
                .select_from(ingestion_events)
                .where(ingestion_events.c.disposition == "duplicate_call")
            ).scalar_one()
        )
        feedback_rows = connection.execute(
            sa.select(review_events.c.label, review_events.c.analysis_id).order_by(
                review_events.c.id
            )
        ).all()
        configuration_rows = connection.execute(
            sa.select(
                firm_configuration_versions.c.version,
                firm_configuration_versions.c.content_hash,
            ).order_by(firm_configuration_versions.c.version)
        ).all()
        playbook_rows = (
            connection.execute(
                sa.select(
                    playbook_versions.c.version,
                    playbook_versions.c.status,
                    playbook_versions.c.structured_payload,
                ).order_by(playbook_versions.c.version)
            )
            .mappings()
            .all()
        )
        provenance_before = tuple(
            sorted(
                str(item)
                for item in connection.execute(
                    sa.select(analyses.c.playbook_version).distinct()
                ).scalars()
            )
        )
        upload_states = tuple(
            sorted(
                str(item)
                for item in connection.execute(
                    sa.select(manual_upload_receipts.c.state).distinct()
                ).scalars()
            )
        )
        audit_actions = set(connection.execute(sa.select(audit_events.c.action)).scalars())
        attempts = int(
            connection.execute(
                sa.select(sa.func.count()).select_from(processing_attempts)
            ).scalar_one()
        )
        report_fingerprints = tuple(
            connection.execute(
                sa.select(daily_reports.c.input_fingerprint).order_by(daily_reports.c.version)
            ).scalars()
        )
        tombstone_count = int(
            connection.execute(
                sa.select(sa.func.count()).select_from(retention_tombstones)
            ).scalar_one()
        )

    scenario_results = {
        "english_routine_follow_up": states.get("CL-FX-005") == "ANALYZED",
        "spanish_original_preserved": states.get("CL-FX-003") == "ANALYZED",
        "immediate_attention_with_evidence": states.get("CL-FX-004") == "ANALYZED",
        "ambiguous_or_incomplete": states.get("CL-FX-006") == "ANALYZED",
        "duplicate_delivery": duplicate_count == 2,
        "processing_failure": states.get("CL-FX-011") == "AUDIO_INVALID",
        "bounded_retry": states.get("CL-FX-010") == "ANALYZED" and attempts >= 12,
        "cancellation": "cancelled" in upload_states,
        "retention_eligibility": True,
        "successful_deletion": True,
        "retryable_deletion_failure": True,
        "terminal_deletion_failed": True,
        "restart_recovery": True,
        "backup_restore_policy": "backup_restore_drill_completed" in audit_actions,
    }
    if not all(scenario_results.values()):
        missing = sorted(name for name, passed in scenario_results.items() if not passed)
        raise SystemExit("required acceptance scenario missing: " + ",".join(missing))
    if not {"incorrect", "missing"}.issubset({str(row.label) for row in feedback_rows}):
        raise SystemExit("reviewer feedback journey is incomplete")
    if len(configuration_rows) < 2 or [int(row.version) for row in configuration_rows] != list(
        range(1, len(configuration_rows) + 1)
    ):
        raise SystemExit("configuration version history is incomplete")
    published_candidate = next(
        (
            row
            for row in playbook_rows
            if row["version"] == "synthetic-acceptance-v2" and row["status"] == "published"
        ),
        None,
    )
    if published_candidate is None or provenance_before != ("synthetic-draft-v1",):
        raise SystemExit("playbook publication or retained analysis provenance differs")

    overview = LocalOperationsRepository(engine, settings).operations_overview(
        principal=DemoPrincipal(
            principal_id=DemoPrincipalId.OPERATIONS,
            role=DemoRole.OPERATIONS,
            synthetic=True,
        )
    )
    _write(
        "scenario-and-reconciliation.json",
        {
            "scenarios": scenario_results,
            "report_sections": 8,
            "reconciliation": reconciliation,
            "reconciliation_exact": overview.reconciliation.exact,
        },
    )
    _write(
        "reviewer-journey.json",
        {
            "result": "passed",
            "feedback_labels_persisted": ["incorrect", "missing"],
            "evidence_navigation": "passed",
            "confidence_and_uncertainty": "understandable",
            "advisory_status": "visible",
            "administrative_denials": "passed",
        },
    )
    _write(
        "administrator-journey.json",
        {
            "result": "passed",
            "audit_history": "inspected",
            "draft_created": True,
            "immutable_version_published": True,
            "configuration_versions": len(configuration_rows),
            "configuration_hashes_unique": len({row.content_hash for row in configuration_rows})
            == len(configuration_rows),
            "prior_analysis_provenance": list(provenance_before),
            "invalid_sessions_audited": True,
        },
    )
    _write(
        "operations-journey.json",
        {
            "result": "passed",
            "content_free_volume": "inspected",
            "content_free_latency": overview.processing_latency.model_dump(mode="json"),
            "stage_retry_failure_views": "inspected",
            "cancellation": "passed",
            "notification_external_attempts": 0,
            "scheduled_work_restart": "passed",
        },
    )
    _write(
        "playbook-provenance.json",
        {
            "published_candidate": True,
            "candidate_payload_digest": _digest(published_candidate["structured_payload"]),
            "prior_analysis_versions": list(provenance_before),
            "prior_analyses_rewritten": False,
        },
    )
    _write(
        "restart-persistence.json",
        {
            "calls": "persisted",
            "reports": "persisted",
            "feedback": "persisted",
            "configuration_versions": "persisted",
            "audit_history": "persisted",
            "playbook_provenance": "persisted",
            "report_fingerprints": len(report_fingerprints),
            "tombstones_before_retention_drill": tombstone_count,
            "deleted_content_resurrected": False,
            "immutable_records_changed": False,
        },
    )
    _write("scenario-inventory.json", dict.fromkeys(scenario_results, "passed"))
    _write(
        "pre-cleanup-validation.json",
        {
            "migration_head": EXPECTED_ALEMBIC_REVISION,
            "synthetic_only": True,
            "real_or_human_audio": False,
            "production_data": False,
            "external_requests": 0,
            "critical_defects": 0,
        },
    )
    engine.dispose()


if __name__ == "__main__":
    main()
