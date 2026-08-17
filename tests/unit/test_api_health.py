from __future__ import annotations

from fastapi.testclient import TestClient

from apps.api.colacci_api import create_app
from packages.config import Settings


def test_liveness_is_content_free_and_synthetic() -> None:
    app = create_app(Settings(_env_file=None))
    with TestClient(app) as client:
        response = client.get("/health/live", headers={"X-Correlation-ID": "slice0-test-001"})

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == "slice0-test-001"
    assert response.json() == {
        "status": "up",
        "service": "api",
        "profile": "demo",
        "version": "0.1.0",
        "synthetic_data": True,
        "database": "not_checked",
        "migration": "not_checked",
    }


def test_readiness_fails_closed_without_database_details() -> None:
    settings = Settings(
        _env_file=None,
        database_url=(
            "postgresql+psycopg://sensitive-user:sensitive-password@127.0.0.1:1/missing"
            "?connect_timeout=1"
        ),
    )
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["database"] == "not_ready"
    assert "sensitive" not in response.text


def test_request_logging_ignores_headers_query_and_invalid_correlation_id(caplog: object) -> None:
    app = create_app(Settings(_env_file=None))
    with TestClient(app) as client:
        response = client.get(
            "/health/live?transcript=never-log-this-content",
            headers={
                "Authorization": "Bearer never-log-this-token",
                "X-Correlation-ID": "invalid value with spaces",
            },
        )

    assert response.status_code == 200
    assert " " not in response.headers["X-Correlation-ID"]
    captured = str(caplog.text)
    assert "never-log-this-content" not in captured
    assert "never-log-this-token" not in captured
    assert "transcript" not in captured
    assert '"route":"/health/live"' in captured
