from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import DBAPIError

from apps.api.colacci_api import create_app
from packages.config import Settings
from packages.contracts.operations import DEFAULT_LOCAL_FIRM_CONFIGURATION, DeletionState
from packages.contracts.report import DemoPrincipal, DemoPrincipalId, DemoRole
from packages.contracts.review import PlaybookVersion
from packages.database.local_operations import (
    LocalOperationsRepository,
    ScriptedDeletionFailures,
)
from packages.database.repository import ReviewRepository
from packages.database.review_experience import ReviewExperienceRepository
from packages.database.review_schema import (
    analyses,
    audit_events,
    calls,
    firm_configuration_versions,
    manual_upload_receipts,
    media_artifacts,
    retention_jobs,
    retention_tombstones,
    review_events,
    transcripts,
)
from packages.media.store import LocalSyntheticObjectStore
from packages.review.fixtures import FixtureCallSource
from packages.review.pipeline import FixturePipeline

pytestmark = pytest.mark.integration

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
class MutableClock:
    value: datetime

    def now(self) -> datetime:
        return self.value


def _reset_and_seed() -> tuple[Settings, sa.Engine, dict[str, str]]:
    settings = Settings(_env_file=None, app_profile="test")
    parsed = urlsplit(settings.sqlalchemy_database_url.replace("postgresql+psycopg", "postgresql"))
    assert parsed.path.endswith("_test")
    alembic = Config("alembic.ini")
    alembic.set_main_option("sqlalchemy.url", settings.sqlalchemy_database_url)
    command.downgrade(alembic, "base")
    command.upgrade(alembic, "head")
    engine = create_engine(settings.sqlalchemy_database_url)
    source = FixtureCallSource()
    repository = ReviewRepository(engine)
    playbook = PlaybookVersion.model_validate_json(
        Path("fixtures/playbooks/synthetic-draft-v1.json").read_text(encoding="utf-8")
    )
    repository.install_playbook(playbook.model_dump(mode="json"))
    pipeline = FixturePipeline(repository, source=source)
    call_ids: dict[str, str] = {}
    for event in source.events():
        outcome = pipeline.process(event)
        call_ids[event.fixture_id] = outcome.call_id
    pipeline.process(source.events("CL-FX-002")[0])
    expected = tuple(sorted({event.call.source_call_id for event in source.events()}))
    ReviewExperienceRepository(engine).generate_report(
        business_date=date(2026, 8, 17),
        cutoff_at=datetime(2026, 8, 17, 18, tzinfo=ZoneInfo("America/New_York")),
        expected_source_call_ids=expected,
    )
    return settings, engine, call_ids


def test_configuration_operations_routes_and_complete_demo_authorization() -> None:
    settings, engine, _ = _reset_and_seed()
    try:
        repository = LocalOperationsRepository(engine, settings)
        history = repository.configuration_history()
        assert history.current_version == 1
        original_analysis = (
            engine.connect()
            .execute(sa.select(analyses.c.original_payload).order_by(analyses.c.id).limit(1))
            .scalar_one()
        )
        changed = DEFAULT_LOCAL_FIRM_CONFIGURATION.model_copy(
            update={"daily_report_cutoff": "17:30"}
        )
        published = repository.publish_configuration(changed, principal=ADMIN)
        assert published.version == 2
        assert repository.configuration_history().versions[-1].version == 1
        with pytest.raises(PermissionError, match="forbidden"):
            repository.publish_configuration(
                changed.model_copy(update={"daily_report_cutoff": "17:45"}),
                principal=OPERATIONS,
            )
        assert (
            engine.connect()
            .execute(sa.select(analyses.c.original_payload).order_by(analyses.c.id).limit(1))
            .scalar_one()
            == original_analysis
        )

        app = create_app(settings)
        with TestClient(app) as client:
            allowed = {
                "demo-admin": (200, 200, 200),
                "demo-operations": (200, 200, 200),
                "demo-reviewer": (403, 403, 403),
            }
            for principal, expected in allowed.items():
                headers = {"X-Demo-Principal": principal}
                assert (
                    client.get("/api/operations/overview", headers=headers).status_code
                    == expected[0]
                )
                assert (
                    client.get("/api/operations/configuration", headers=headers).status_code
                    == expected[1]
                )
                assert (
                    client.get("/api/operations/deletions", headers=headers).status_code
                    == expected[2]
                )
            assert client.get("/api/operations/overview").status_code == 401
            assert (
                client.get(
                    "/api/operations/overview", headers={"X-Demo-Principal": "invalid-demo"}
                ).status_code
                == 401
            )
            assert (
                client.get(
                    "/api/operations/overview",
                    headers={"X-Demo-Principal": "demo-admin", "X-Demo-Session": "expired"},
                ).status_code
                == 401
            )
            spoofed = client.get(
                "/api/operations/overview",
                headers={
                    "X-Demo-Principal": "demo-reviewer",
                    "X-Demo-Role": "administrator",
                },
            )
            assert spoofed.status_code == 403

            config_payload = changed.model_copy(update={"daily_report_cutoff": "17:15"}).model_dump(
                mode="json"
            )
            assert (
                client.post(
                    "/api/operations/configuration",
                    headers={"X-Demo-Principal": "demo-admin", "X-Demo-Role": "reviewer"},
                    json=config_payload,
                ).status_code
                == 201
            )
            assert (
                client.post(
                    "/api/operations/configuration",
                    headers={"X-Demo-Principal": "demo-operations"},
                    json={**config_payload, "daily_report_cutoff": "17:00"},
                ).status_code
                == 403
            )
            assert (
                client.post(
                    "/api/operations/configuration",
                    headers={"X-Demo-Principal": "demo-admin"},
                    json={**config_payload, "production_project": "forbidden"},
                ).status_code
                == 422
            )

            for path in (
                "/api/operations/retention/run",
                "/api/operations/backup-restore-drill",
                "/api/operations/notification-preview",
            ):
                assert (
                    client.post(path, headers={"X-Demo-Principal": "demo-reviewer"}).status_code
                    == 403
                )
            assert (
                client.get(
                    "/api/audit-events", headers={"X-Demo-Principal": "demo-reviewer"}
                ).status_code
                == 403
            )
            for principal in ("demo-admin", "demo-operations"):
                assert (
                    client.get(
                        "/api/audit-events", headers={"X-Demo-Principal": principal}
                    ).status_code
                    == 200
                )

        with engine.connect() as connection:
            actions = set(connection.execute(sa.select(audit_events.c.action)).scalars())
            assert {
                "demo_identity_missing",
                "demo_identity_invalid",
                "demo_session_expired",
                "caller_role_ignored",
                "configuration_published",
                "configuration_publish_denied",
                "operations_overview_view_denied",
            }.issubset(actions)
            assert (
                connection.execute(
                    sa.select(sa.func.count()).select_from(firm_configuration_versions)
                ).scalar_one()
                == 3
            )
    finally:
        engine.dispose()


def test_retention_deletion_retry_terminal_restart_idempotency_and_tombstones() -> None:
    settings, engine, call_ids = _reset_and_seed()
    clock = MutableClock(datetime(2038, 1, 1, 12, tzinfo=UTC))
    old = datetime(2020, 1, 1, 12, tzinfo=UTC)
    fresh = clock.value - timedelta(days=1)
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
                client_submission_id="synthetic-retention-receipt",
                source_event_id="synthetic-retention-event",
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
                note="Invented retention-only feedback.",
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
                action="synthetic_retention_seeded",
                target_type="local_operations",
                target_id="retention-seed",
                result="created",
                created_at=old,
            )
        )
    with engine.connect() as connection:
        transcript_ids = tuple(
            str(item)
            for item in connection.execute(
                sa.select(transcripts.c.id).order_by(transcripts.c.id).limit(3)
            ).scalars()
        )
    retry_id, terminal_id, restart_id = transcript_ids
    failures = ScriptedDeletionFailures(
        {
            retry_id: ("temporary_deletion_unavailable", None),
            terminal_id: (
                "temporary_deletion_unavailable",
                "temporary_deletion_unavailable",
                "temporary_deletion_unavailable",
            ),
        }
    )
    repository = LocalOperationsRepository(engine, settings, clock=clock, failure_plan=failures)
    try:
        with pytest.raises(DBAPIError, match="immutable"), engine.begin() as connection:
            connection.execute(
                transcripts.update().where(transcripts.c.id == retry_id).values(original_payload={})
            )

        evaluation = repository.evaluate_retention(principal=ADMIN)
        assert evaluation.scheduled > 0
        assert evaluation.not_due >= 1
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
        assert execution.recovered == 1
        assert execution.deleted > 0
        assert execution.retry_scheduled == 2
        assert execution.retained_exceptions > 0
        assert not store.exists(reference)

        jobs = repository.deletion_jobs()
        retry_job = next(item for item in jobs if item.resource_id == retry_id)
        terminal_job = next(item for item in jobs if item.resource_id == terminal_id)
        assert (
            repository.retry_deletion(retry_job.job_id, principal=OPERATIONS).state
            is DeletionState.DELETED
        )
        assert (
            repository.retry_deletion(terminal_job.job_id, principal=OPERATIONS).state
            is DeletionState.RETRY_SCHEDULED
        )
        terminal_result = repository.retry_deletion(terminal_job.job_id, principal=OPERATIONS)
        assert terminal_result.state is DeletionState.DELETION_FAILED
        assert terminal_result.attempt_count == 3
        with pytest.raises(ValueError, match="not_retryable"):
            repository.retry_deletion(terminal_job.job_id, principal=OPERATIONS)

        rerun = repository.run_retention(principal=ADMIN)
        assert rerun.scheduled == 0
        assert rerun.deleted == 0
        with engine.connect() as connection:
            assert (
                connection.execute(
                    sa.select(sa.func.count())
                    .select_from(media_artifacts)
                    .where(media_artifacts.c.id == "b" * 32)
                ).scalar_one()
                == 1
            )
            tombstone_rows = connection.execute(sa.select(retention_tombstones)).mappings().all()
            assert tombstone_rows
            assert set(tombstone_rows[0]) == {
                "id",
                "resource_type",
                "resource_id",
                "configuration_version",
                "result",
                "exception_code",
                "destroyed_at",
            }
            assert (
                connection.execute(
                    sa.select(sa.func.count())
                    .select_from(retention_tombstones)
                    .where(retention_tombstones.c.result == "retained_exception")
                ).scalar_one()
                > 0
            )
            assert (
                connection.execute(
                    sa.select(sa.func.count())
                    .select_from(calls)
                    .where(calls.c.id == call_ids["CL-FX-002"])
                ).scalar_one()
                == 1
            )
    finally:
        engine.dispose()


def test_disposable_backup_restore_and_noop_notification_are_local_and_clean() -> None:
    settings, engine, _ = _reset_and_seed()
    clock = MutableClock(datetime(2026, 8, 19, 12, tzinfo=UTC))
    repository = LocalOperationsRepository(engine, settings, clock=clock)
    try:
        drill = repository.run_backup_restore_drill(principal=OPERATIONS)
        assert drill.status == "passed"
        assert drill.restored_expired == 0
        assert drill.normal_database_unchanged is True
        assert drill.disposable_artifacts_removed is True
        preview = repository.notification_preview(
            principal=OPERATIONS,
            safe_count=2,
            internal_reference="operations-center",
        )
        assert preview.label == "Local preview - nothing sent"
        assert preview.external_attempts == 0
        overview = repository.operations_overview(principal=OPERATIONS)
        assert overview.backup_restore_status == "passed"
        assert overview.external_requests == 0

        unsafe = settings.model_copy(update={"notification_adapter": "email"})
        with pytest.raises(ValueError, match="boundary_rejected"):
            LocalOperationsRepository(engine, unsafe)
    finally:
        engine.dispose()


def test_reconciliation_unavailable_and_malformed_payloads_do_not_look_exact() -> None:
    unavailable = LocalOperationsRepository._safe_reconciliation(None)
    assert unavailable.available is False
    assert unavailable.exact is False
    assert unavailable.expected == 0

    with pytest.raises(ValueError, match="reconciliation_payload_invalid"):
        LocalOperationsRepository._safe_reconciliation({"completeness": {}})
    with pytest.raises(ValueError, match="reconciliation_payload_invalid"):
        LocalOperationsRepository._safe_reconciliation(
            {
                "completeness": {
                    "reconciliation": {
                        "expected": "11",
                        "received": 11,
                        "analyzed": 10,
                        "failed": 1,
                        "missing": 0,
                    }
                }
            }
        )
