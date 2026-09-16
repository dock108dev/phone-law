"""Exercise real HTTP boundaries with offline repository failure injection."""

from __future__ import annotations

import json
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from apps.api.colacci_api import create_app, operations_routes, review_routes
from apps.api.colacci_api.demo_auth import demo_principal
from packages.config import Settings
from packages.contracts.operations import DEFAULT_LOCAL_FIRM_CONFIGURATION
from packages.contracts.report import DemoPrincipal, DemoPrincipalId, DemoRole
from packages.contracts.review import StructuredAnalysis
from packages.database.errors import ResourceConflictError, ResourceNotFoundError

CASES = [
    (review_routes, "month_history", "GET", "/api/reports/months/2026-09", None),
    (review_routes, "add_review", "POST", "/api/analyses/invented/reviews", {"label": "correct"}),
    (
        review_routes,
        "create_playbook_draft",
        "POST",
        "/api/playbooks/drafts",
        {"version": "synthetic-new", "source_version": "synthetic-old", "label": "Invented"},
    ),
    (review_routes, "publish_playbook", "POST", "/api/playbooks/synthetic-new/publish", None),
    (
        operations_routes,
        "publish_configuration",
        "POST",
        "/api/operations/configuration",
        DEFAULT_LOCAL_FIRM_CONFIGURATION.model_dump(mode="json"),
    ),
    (operations_routes, "retry_deletion", "POST", "/api/operations/deletions/invented/retry", None),
]


def stored_validation_error():
    with pytest.raises(ValidationError) as caught:
        StructuredAnalysis.model_validate({"private-field": "private-record-content"})
    return caught.value


@pytest.mark.parametrize("module,method,verb,path,payload", CASES)
@pytest.mark.parametrize(
    "failure",
    [
        KeyError("private-record-content"),
        IndexError("private-record-content"),
        LookupError("private-record-content"),
        ValueError("private-record-content"),
        stored_validation_error(),
    ],
)
def test_unexpected_repository_errors_are_private_500s(
    monkeypatch, caplog, module, method, verb, path, payload, failure
):
    app = create_app(Settings(_env_file=None))
    app.dependency_overrides[demo_principal] = lambda: DemoPrincipal(
        principal_id=DemoPrincipalId.ADMIN, role=DemoRole.ADMINISTRATOR
    )
    repository = Mock()
    getattr(repository, method).side_effect = failure
    monkeypatch.setattr(module, "_repository", lambda request: repository)
    # Authorization remains enabled; only its database audit sink is replaced.
    monkeypatch.setattr(operations_routes, "ReviewExperienceRepository", lambda engine: Mock())
    with TestClient(app) as client:
        for _ in range(2):
            response = client.request(
                verb, path, json=payload, headers={"X-Correlation-ID": "repository-fault-001"}
            )
            assert response.status_code == 500
            assert response.json()["detail"] == {
                "error": "internal_error",
                "correlation_id": "repository-fault-001",
            }
            assert response.headers["Cache-Control"] == "no-store"
            assert response.headers["X-Correlation-ID"] == "repository-fault-001"
            assert "private-record-content" not in response.text
    events = [json.loads(message) for message in caplog.messages if '"event"' in message]
    failures = [event for event in events if event["event"] == "http_request_failed"]
    assert len(failures) == 2
    assert all(event["exception_frames"] and event["level"] == "error" for event in failures)
    assert "private-record-content" not in caplog.text


@pytest.mark.parametrize("module,method,verb,path,payload", CASES)
@pytest.mark.parametrize(
    "error_type,expected_status", [(ResourceNotFoundError, 404), (ResourceConflictError, 409)]
)
def test_expected_repository_outcomes_keep_their_status(
    monkeypatch, module, method, verb, path, payload, error_type, expected_status
):
    if method == "month_history" and error_type is ResourceConflictError:
        pytest.skip("Month lookup has no conflict outcome")
    if method == "publish_configuration" and error_type is ResourceNotFoundError:
        pytest.skip("Configuration publication has no missing-resource outcome")
    app = create_app(Settings(_env_file=None))
    app.dependency_overrides[demo_principal] = lambda: DemoPrincipal(
        principal_id=DemoPrincipalId.ADMIN, role=DemoRole.ADMINISTRATOR
    )
    repository = Mock()
    getattr(repository, method).side_effect = error_type("expected_fixed_code")
    monkeypatch.setattr(module, "_repository", lambda request: repository)
    monkeypatch.setattr(operations_routes, "ReviewExperienceRepository", lambda engine: Mock())
    with TestClient(app) as client:
        response = client.request(verb, path, json=payload)
    assert response.status_code == expected_status
    expected_code = (
        "deletion_job_not_found"
        if method == "retry_deletion" and error_type is ResourceNotFoundError
        else "expected_fixed_code"
    )
    assert response.json()["detail"]["error"] == expected_code
