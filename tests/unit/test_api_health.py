from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from apps.api.colacci_api import create_app
from apps.api.colacci_api.demo_auth import demo_principal
from packages.config import AppProfile, Settings
from packages.contracts.report import DemoPrincipalId, DemoRole


def test_liveness_is_content_free_and_synthetic() -> None:
    app = create_app(Settings(_env_file=None))
    with TestClient(app) as client:
        response = client.get("/health/live", headers={"X-Correlation-ID": "slice0-test-001"})

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == "slice0-test-001"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Content-Security-Policy"].startswith("default-src 'none'")
    assert response.headers["Cross-Origin-Opener-Policy"] == "same-origin"
    assert response.headers["Cross-Origin-Resource-Policy"] == "same-origin"
    assert response.headers["Permissions-Policy"] == "camera=(), microphone=(), geolocation=()"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Robots-Tag"] == "noindex, nofollow, noarchive"
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


def test_demo_identity_is_allowlisted_and_synthetic_profiles_only() -> None:
    app = FastAPI()
    app.state.settings = Settings(_env_file=None)
    request = Request(
        {"type": "http", "method": "GET", "path": "/api/reports/dates", "headers": [], "app": app}
    )
    request.state.correlation_id = "demo-auth-test"
    principal = demo_principal(request, "demo-admin")
    assert principal.principal_id is DemoPrincipalId.ADMIN
    assert principal.role is DemoRole.ADMINISTRATOR

    with pytest.raises(HTTPException) as missing:
        demo_principal(request, None)
    assert missing.value.status_code == 401
    with pytest.raises(HTTPException) as arbitrary:
        demo_principal(request, "arbitrary-role")
    assert arbitrary.value.status_code == 401

    app.state.settings = app.state.settings.model_copy(update={"app_profile": AppProfile.STAGING})
    with pytest.raises(HTTPException) as deployment:
        demo_principal(request, "demo-admin")
    assert deployment.value.status_code == 404


def test_untrusted_host_is_rejected_before_route_execution() -> None:
    app = create_app(Settings(_env_file=None))
    with TestClient(app) as client:
        response = client.get("/health/live", headers={"Host": "attacker.invalid"})

    assert response.status_code == 400
    assert response.text == "Invalid host header"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
