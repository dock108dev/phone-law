from __future__ import annotations

from apps.worker.colacci_worker.health import liveness_payload, readiness_payload
from packages.config import Settings
from packages.database.health import create_database_engine


def test_worker_liveness_is_synthetic_and_does_not_touch_database() -> None:
    payload = liveness_payload(Settings(_env_file=None))
    assert payload.status == "up"
    assert payload.service == "worker"
    assert payload.synthetic_data is True
    assert payload.database == "not_checked"


def test_worker_readiness_fails_closed_without_database_details() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://user:password@127.0.0.1:1/missing?connect_timeout=1",
    )
    engine = create_database_engine(settings.sqlalchemy_database_url)
    try:
        status_code, payload, error_code = readiness_payload(settings, engine)
    finally:
        engine.dispose()

    assert status_code == 503
    assert payload.status == "not_ready"
    assert error_code == "database_unavailable_or_unmigrated"
