from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlsplit

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError

from apps.api.colacci_api import create_app
from apps.worker.colacci_worker.health import readiness_payload
from packages.config import Settings
from packages.database.health import EXPECTED_ALEMBIC_REVISION, create_database_engine
from packages.database.review_schema import media_artifacts, transcription_provider_attempts

pytestmark = pytest.mark.integration


def test_empty_database_migrates_and_all_components_become_ready() -> None:
    settings = Settings(_env_file=None, app_profile="test")
    parsed = urlsplit(settings.sqlalchemy_database_url.replace("postgresql+psycopg", "postgresql"))
    assert parsed.path.endswith("_test"), "migration test may operate only on the test database"

    alembic = Config("alembic.ini")
    alembic.set_main_option("sqlalchemy.url", settings.sqlalchemy_database_url)
    command.downgrade(alembic, "base")
    command.upgrade(alembic, "head")

    engine = create_engine(settings.sqlalchemy_database_url)
    try:
        expected_tables = {
            "alembic_version",
            "analyses",
            "audit_events",
            "backup_restore_drills",
            "calls",
            "daily_report_items",
            "daily_reports",
            "ingestion_events",
            "firm_configuration_versions",
            "maintenance_runs",
            "media_artifacts",
            "media_lifecycle_events",
            "manual_upload_receipts",
            "manual_upload_state_events",
            "notification_previews",
            "playbook_versions",
            "processing_attempts",
            "review_events",
            "retention_jobs",
            "retention_tombstones",
            "system_metadata",
            "transcripts",
            "transcription_provider_attempts",
        }
        assert expected_tables == set(inspect(engine).get_table_names())
        with engine.connect() as connection:
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            purpose = connection.execute(
                text("SELECT value FROM system_metadata WHERE key = 'schema_purpose'")
            ).scalar_one()
        assert revision == EXPECTED_ALEMBIC_REVISION
        assert purpose == "local_operations"

        # Historical rows remain readable; retirement removes writers, not stored evidence.
        artifact_id = "0123456789abcdef0123456789abcdef"
        attempt_id = "3123456789abcdef0123456789abcdef"
        with engine.begin() as connection:
            connection.execute(
                media_artifacts.insert().values(
                    id=artifact_id,
                    is_synthetic=True,
                    content_hash_reference="sha256:" + "a" * 12,
                    media_format="wav",
                    byte_size=32044,
                    duration_seconds=1.0,
                    channel_count=1,
                    sample_rate_hz=16000,
                    lifecycle_state="INSPECTED",
                    created_at=datetime.now(UTC),
                )
            )
            connection.execute(
                transcription_provider_attempts.insert().values(
                    id=attempt_id,
                    artifact_id=artifact_id,
                    attempt_number=1,
                    adapter_version="historical-synthetic-v1",
                    model_id="historical-model",
                    retryable=False,
                    duration_ms=10,
                    created_at=datetime.now(UTC),
                )
            )
        command.upgrade(alembic, "head")
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT model_id FROM transcription_provider_attempts WHERE id = :id"),
                    {"id": attempt_id},
                ).scalar_one()
                == "historical-model"
            )
        with pytest.raises(DBAPIError, match="immutable"), engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE media_artifacts SET byte_size = 1 "
                    "WHERE id = '0123456789abcdef0123456789abcdef'"
                )
            )

        command.downgrade(alembic, "0004_offline_transcription_readiness")
        assert not {
            "manual_upload_receipts",
            "manual_upload_state_events",
            "firm_configuration_versions",
            "retention_jobs",
            "retention_tombstones",
            "maintenance_runs",
            "backup_restore_drills",
            "notification_previews",
        }.intersection(inspect(engine).get_table_names())
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                == "0004_offline_transcription_readiness"
            )
            assert (
                connection.execute(
                    text("SELECT value FROM system_metadata WHERE key = 'schema_purpose'")
                ).scalar_one()
                == "offline_transcription_readiness"
            )

        command.upgrade(alembic, "head")
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT model_id FROM transcription_provider_attempts WHERE id = :id"),
                    {"id": attempt_id},
                ).scalar_one()
                == "historical-model"
            )

        command.downgrade(alembic, "0003_synthetic_review_experience")
        assert not {
            "media_artifacts",
            "media_lifecycle_events",
            "transcription_provider_attempts",
        }.intersection(inspect(engine).get_table_names())
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                == "0003_synthetic_review_experience"
            )
        command.upgrade(alembic, "head")
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                == EXPECTED_ALEMBIC_REVISION
            )
    finally:
        engine.dispose()

    app = create_app(settings)
    with TestClient(app) as client:
        api_response = client.get("/health/ready")
    assert api_response.status_code == 200
    assert api_response.json()["migration"] == "current"

    worker_engine = create_database_engine(settings.sqlalchemy_database_url)
    try:
        status_code, worker_response, error_code = readiness_payload(settings, worker_engine)
    finally:
        worker_engine.dispose()
    assert status_code == 200
    assert worker_response.status == "ready"
    assert error_code is None
