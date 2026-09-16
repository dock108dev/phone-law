from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from apps.api.colacci_api.app import create_app
from apps.api.colacci_api.origin_boundary import MutationOriginMiddleware
from packages.config import Settings
from packages.observability.logging import OperationalLogger


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize(
    "origins",
    [
        ["https://unapproved.invalid/private-sentinel"],
        ["null"],
        [""],
        ["http://localhost:15173.attacker.invalid"],
        ["http://localhost:15173/"],
        ["http://localhost:15173", "https://unapproved.invalid"],
        ["http://localhost:15173", "http://localhost:15173"],
    ],
)
def test_unapproved_origin_never_reads_body_or_calls_application(method, origins, caplog):
    async def run():
        async def forbidden(*args):
            pytest.fail("Origin rejection must precede body reads and application side effects")

        messages = []

        async def send(message):
            messages.append(message)

        middleware = MutationOriginMiddleware(
            forbidden,
            allowed_origins=["http://localhost:15173"],
            logger=OperationalLogger("origin-test"),
        )
        await middleware(
            {
                "type": "http",
                "method": method,
                "scheme": "http",
                "path": "/api/playbooks/drafts",
                "query_string": b"",
                "headers": [(b"host", b"testserver")]
                + [(b"origin", origin.encode()) for origin in origins],
                "state": {"correlation_id": "security-origin-001"},
            },
            forbidden,
            send,
        )
        assert messages[0]["status"] == 403
        assert b"mutation_origin_forbidden" in messages[1]["body"]
        assert b"private-sentinel" not in messages[1]["body"]

    asyncio.run(run())
    assert "mutation_origin_rejected" in caplog.text
    assert "private-sentinel" not in caplog.text


@pytest.mark.parametrize(
    "origin", [None, "http://localhost:15173", "http://testserver", "http://web:5173"]
)
def test_supported_local_mutations_still_reach_handler(origin):
    app = create_app(Settings(_env_file=None))

    @app.post("/origin-probe")
    async def endpoint():
        return {"accepted": True}

    base = "http://web:5173" if origin == "http://web:5173" else "http://testserver"
    with TestClient(app, base_url=base) as client:
        response = client.post("/origin-probe", headers={"Origin": origin} if origin else {})
    assert response.status_code == 200
    assert response.json() == {"accepted": True}


def test_rejection_keeps_safe_headers_and_does_not_trust_forwarded_host():
    app = create_app(Settings(_env_file=None))
    with TestClient(app) as client:
        response = client.post(
            "/api/playbooks/drafts",
            content=b"invalid JSON",
            headers={
                "Origin": "https://unapproved.invalid",
                "X-Forwarded-Host": "unapproved.invalid",
                "X-Correlation-ID": "security-origin-002",
            },
        )
    assert response.status_code == 403
    assert response.json()["detail"] == {
        "error": "mutation_origin_forbidden",
        "correlation_id": "security-origin-002",
    }
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "Access-Control-Allow-Origin" not in response.headers


def test_matching_origin_cannot_bypass_trusted_host():
    app = create_app(Settings(_env_file=None))
    with TestClient(app, base_url="http://unapproved.invalid") as client:
        response = client.post(
            "/api/playbooks/drafts", headers={"Origin": "http://unapproved.invalid"}
        )
    assert response.status_code == 400


def test_health_and_cors_preflight_remain_available():
    app = create_app(Settings(_env_file=None))
    with TestClient(app) as client:
        assert client.get("/health/live", headers={"Origin": "null"}).status_code == 200
        response = client.options(
            "/api/playbooks/drafts",
            headers={
                "Origin": "http://localhost:15173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "X-Demo-Principal, Content-Type",
            },
        )
    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:15173"


@pytest.mark.parametrize("origin", [None, "http://testserver", "http://localhost:15173"])
def test_origin_admission_does_not_replace_route_authentication(origin, monkeypatch):
    monkeypatch.setattr("apps.api.colacci_api.demo_auth._audit_auth", lambda *a, **kw: None)
    app = create_app(Settings(_env_file=None))
    with TestClient(app) as client:
        response = client.post(
            "/api/uploads/example/process", headers={"Origin": origin} if origin else {}
        )
    assert response.status_code == 401
