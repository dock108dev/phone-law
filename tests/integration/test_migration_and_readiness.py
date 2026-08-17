from __future__ import annotations

from urllib.parse import urlsplit

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

from apps.api.colacci_api import create_app
from apps.worker.colacci_worker.health import readiness_payload
from packages.config import Settings
from packages.database.health import EXPECTED_ALEMBIC_REVISION, create_database_engine

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
            "calls",
            "ingestion_events",
            "playbook_versions",
            "processing_attempts",
            "system_metadata",
            "transcripts",
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
        assert purpose == "synthetic_review_contracts"
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
