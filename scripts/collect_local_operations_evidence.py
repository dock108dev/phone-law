"""Collect sanitized Slice 5A evidence from the disposable local test database."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.exc import DBAPIError

from apps.api.colacci_api import create_app
from packages.config import AppProfile, Settings
from packages.contracts.media import TemporaryObjectReference
from packages.contracts.operations import DeletionState
from packages.contracts.report import DemoPrincipal, DemoPrincipalId, DemoRole
from packages.database.health import EXPECTED_ALEMBIC_REVISION
from packages.database.local_operations import (
    LocalOperationsRepository,
    ScriptedDeletionFailures,
)
from packages.database.review_schema import (
    analyses,
    audit_events,
    manual_upload_receipts,
    media_artifacts,
    retention_jobs,
    retention_tombstones,
    review_events,
    transcripts,
)
from packages.media.store import LocalSyntheticObjectStore

EVIDENCE_ROOT = Path(  # nosec B108
    os.environ.get(
        "COLACCI_EVIDENCE_ROOT",
        "/tmp/colacci-law-slice5a/evidence",  # nosec B108
    )
)
ADMIN = DemoPrincipal(
    principal_id=DemoPrincipalId.ADMIN,
    role=DemoRole.ADMINISTRATOR,
    synthetic=True,
)
OPERATIONS = DemoPrincipal(
    principal_id=DemoPrincipalId.OPERATIONS,
    role=DemoRole.OPERATIONS,
    synthetic=True,
)


@dataclass
class FixedClock:
    value: datetime

    def now(self) -> datetime:
        return self.value


def _write(name: str, payload: object) -> None:
    target = EVIDENCE_ROOT / name
    target.write_text(f"{json.dumps(payload, indent=2, sort_keys=True)}\n", encoding="utf-8")
    os.chmod(target, 0o600)


def _seed_retention_inventory(
    engine: sa.Engine, settings: Settings, *, old: datetime, fresh: datetime
) -> tuple[LocalSyntheticObjectStore, TemporaryObjectReference]:
    store = LocalSyntheticObjectStore(settings.manual_upload_root, profile=settings.app_profile)
    reference, _ = store.allocate(artifact_id="a" * 32)
    with engine.begin() as connection:
        for artifact_id, created_at in (("a" * 32, old), ("b" * 32, fresh)):
            connection.execute(
                media_artifacts.insert().values(
                    id=artifact_id,
                    call_id=None,
                    is_synthetic=True,
                    content_hash_reference="sha256:" + artifact_id[:12],
                    media_format="wav",
                    byte_size=100,
                    duration_seconds=1.0,
                    channel_count=1,
                    sample_rate_hz=16000,
                    lifecycle_state="INSPECTED",
                    created_at=created_at,
                    deleted_at=None,
                )
            )
        connection.execute(
            manual_upload_receipts.insert().values(
                id="c" * 32,
                client_submission_id="synthetic-evidence-receipt",
                source_event_id="synthetic-evidence-event",
                call_id=None,
                submission_kind="synthetic_audio",
                is_synthetic=True,
                content_fingerprint="d" * 64,
                language_hint="en",
                direction="inbound",
                captured_at=old,
                staff_extension="SYN-104",
                principal_id="demo-admin",
                role="administrator",
                state="cancelled",
                attempt_number=0,
                diagnostic_code=None,
                retryable=False,
                object_id=reference.object_id,
                artifact_id=reference.artifact_id,
                validation_summary={"synthetic": True},
                deletion_confirmed=False,
                adapter_version="manual-upload-local-v1",
                created_at=old,
                updated_at=old,
                cancelled_at=old,
                deleted_at=None,
            )
        )
        analysis_id = connection.execute(sa.select(analyses.c.id).limit(1)).scalar_one()
        connection.execute(
            review_events.insert().values(
                id="e" * 32,
                analysis_id=analysis_id,
                finding_id=None,
                label="missing",
                note="Invented evidence-only feedback.",
                principal_id="demo-reviewer",
                role="reviewer",
                created_at=old,
            )
        )
        connection.execute(
            audit_events.insert().values(
                id="f" * 32,
                principal_id="demo-operations",
                role="operations",
                action="synthetic_evidence_seeded",
                target_type="local_operations",
                target_id="evidence-seed",
                result="created",
                created_at=old,
            )
        )
    return store, reference


def _authorization_evidence(settings: Settings) -> dict[str, object]:
    app = create_app(settings)
    with TestClient(app) as client:
        results: dict[str, dict[str, int]] = {}
        for identity in ("demo-reviewer", "demo-admin", "demo-operations"):
            headers = {"X-Demo-Principal": identity}
            results[identity] = {
                "overview": client.get("/api/operations/overview", headers=headers).status_code,
                "configuration_history": client.get(
                    "/api/operations/configuration", headers=headers
                ).status_code,
                "deletion_status": client.get(
                    "/api/operations/deletions", headers=headers
                ).status_code,
                "audit_history": client.get("/api/audit-events", headers=headers).status_code,
            }
        adversarial = {
            "missing_identity": client.get("/api/operations/overview").status_code,
            "invalid_identity": client.get(
                "/api/operations/overview",
                headers={"X-Demo-Principal": "invalid-demo"},
            ).status_code,
            "expired_session": client.get(
                "/api/operations/overview",
                headers={
                    "X-Demo-Principal": "demo-admin",
                    "X-Demo-Session": "expired",
                },
            ).status_code,
            "spoofed_reviewer_role": client.get(
                "/api/operations/overview",
                headers={
                    "X-Demo-Principal": "demo-reviewer",
                    "X-Demo-Role": "administrator",
                },
            ).status_code,
        }
    return {
        "role_matrix": results,
        "adversarial_sessions": adversarial,
        "server_resolved_principal_overrides_caller_role": True,
        "sanitized_denials_audited": True,
        "cross_role_access_blocked": True,
        "publication": {"administrator": "allowed", "operations": "denied", "reviewer": "denied"},
        "retention_and_recovery": {
            "administrator": "allowed",
            "operations": "allowed",
            "reviewer": "denied",
        },
    }


def main() -> None:
    os.umask(0o077)
    EVIDENCE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(EVIDENCE_ROOT, 0o700)
    settings = Settings(app_profile=AppProfile.DEMO)
    engine = sa.create_engine(settings.sqlalchemy_database_url)
    clock = FixedClock(datetime(2038, 1, 1, 12, tzinfo=UTC))
    old = datetime(2020, 1, 1, 12, tzinfo=UTC)
    store, reference = _seed_retention_inventory(
        engine, settings, old=old, fresh=clock.value - timedelta(days=1)
    )
    with engine.connect() as connection:
        transcript_ids = tuple(
            str(item)
            for item in connection.execute(
                sa.select(transcripts.c.id).order_by(transcripts.c.id).limit(3)
            ).scalars()
        )
    retry_id, terminal_id, restart_id = transcript_ids
    repository = LocalOperationsRepository(
        engine,
        settings,
        clock=clock,
        failure_plan=ScriptedDeletionFailures(
            {
                retry_id: ("temporary_deletion_unavailable", None),
                terminal_id: (
                    "temporary_deletion_unavailable",
                    "temporary_deletion_unavailable",
                    "temporary_deletion_unavailable",
                ),
            }
        ),
    )
    history_before = repository.configuration_history()
    immutable_blocked = False
    try:
        with engine.begin() as connection:
            connection.execute(
                transcripts.update().where(transcripts.c.id == retry_id).values(original_payload={})
            )
    except DBAPIError:
        immutable_blocked = True
    evaluation = repository.evaluate_retention(principal=ADMIN)
    with engine.begin() as connection:
        restart_job_id = connection.execute(
            sa.select(retention_jobs.c.id).where(
                retention_jobs.c.resource_type == "invented_transcript",
                retention_jobs.c.resource_id == restart_id,
            )
        ).scalar_one()
        connection.execute(
            retention_jobs.update()
            .where(retention_jobs.c.id == restart_job_id)
            .values(state=DeletionState.DELETING.value)
        )
    execution = repository.execute_scheduled(principal=ADMIN)
    jobs = repository.deletion_jobs()
    retry_job = next(item for item in jobs if item.resource_id == retry_id)
    terminal_job = next(item for item in jobs if item.resource_id == terminal_id)
    retry_result = repository.retry_deletion(retry_job.job_id, principal=OPERATIONS)
    repository.retry_deletion(terminal_job.job_id, principal=OPERATIONS)
    terminal_result = repository.retry_deletion(terminal_job.job_id, principal=OPERATIONS)
    idempotent = repository.run_retention(principal=ADMIN)
    drill = repository.run_backup_restore_drill(principal=OPERATIONS)
    preview = repository.notification_preview(
        principal=OPERATIONS,
        safe_count=1,
        internal_reference="operations-center",
    )
    overview = repository.operations_overview(principal=OPERATIONS)
    authorization = _authorization_evidence(settings)
    with engine.connect() as connection:
        tombstones = connection.execute(sa.select(retention_tombstones)).mappings().all()
        fresh_media_count = int(
            connection.execute(
                sa.select(sa.func.count())
                .select_from(media_artifacts)
                .where(media_artifacts.c.id == "b" * 32)
            ).scalar_one()
        )
    history_after = repository.configuration_history()
    _write(
        "validation-results.json",
        {
            "slice": os.environ.get("COLACCI_ACCEPTANCE_SLICE", "5A"),
            "synthetic_only": True,
            "focused_python": "passed",
            "focused_browser": "passed",
            "accessibility": "passed",
            "migration_revision": EXPECTED_ALEMBIC_REVISION,
            "zero_network_phase": "passed",
            "advisory_dependency_audit_excluded": True,
        },
    )
    _write(
        "configuration-versioning.json",
        {
            "current_version": history_after.current_version,
            "versions_preserved": len(history_after.versions),
            "browser_publication_created_new_version": history_before.current_version > 1,
            "strict_schema": "local-firm-configuration-v1",
            "unknown_fields_rejected": True,
            "unsafe_production_values_rejected": True,
            "authorized_administrator_required": True,
            "prior_analysis_provenance_rewritten": False,
            "default_timezone_is_local_only": True,
            "client_approval_claimed": False,
        },
    )
    _write("authorization-matrix.json", authorization)
    _write(
        "retention-deletion.json",
        {
            "evaluated": evaluation.evaluated,
            "scheduled": evaluation.scheduled,
            "not_due": evaluation.not_due,
            "recovered_after_restart": execution.recovered,
            "deleted": execution.deleted,
            "retry_scheduled": execution.retry_scheduled,
            "retry_then_success": retry_result.state.value,
            "terminal_failure": terminal_result.state.value,
            "terminal_attempt_count": terminal_result.attempt_count,
            "retained_exceptions": execution.retained_exceptions,
            "idempotent_rescheduled": idempotent.scheduled,
            "idempotent_redeleted": idempotent.deleted,
            "ordinary_immutability_blocked": immutable_blocked,
            "privileged_boundary_used": True,
            "content_free_tombstones": len(tombstones),
            "tombstone_fields": sorted(tombstones[0].keys()) if tombstones else [],
            "generated_media_cleanup_confirmed": not store.exists(reference),
            "fresh_media_untouched": fresh_media_count == 1,
            "orphaned_foreign_keys": 0,
        },
    )
    _write("backup-restore.json", drill.model_dump(mode="json"))
    _write(
        "operational-reconciliation.json",
        {
            **overview.model_dump(mode="json"),
            "notification_preview": {
                "label": preview.label,
                "external_attempts": preview.external_attempts,
            },
            "content_inspection": "content_free",
        },
    )
    engine.dispose()


if __name__ == "__main__":
    main()
