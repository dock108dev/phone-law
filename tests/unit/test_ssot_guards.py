from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from packages.contracts.review import SCHEMA_VERSION, Provenance, Transcript
from packages.review.fixtures import FixtureCallSource, FixtureTranscriber

ROOT = Path(__file__).parents[2]
ROUTE_MODULES = (
    ROOT / "apps/api/colacci_api/review_routes.py",
    ROOT / "apps/api/colacci_api/operations_routes.py",
    ROOT / "apps/api/colacci_api/upload_routes.py",
)


def _accepted_transcript() -> Transcript:
    source = FixtureCallSource()
    event = source.events("CL-FX-001")[0]
    provenance = Provenance(
        schema_version=cast(Any, SCHEMA_VERSION),
        call_source=event.call.source,
        source_event_id=event.call.source_event_id,
        source_call_id=event.call.source_call_id,
        transcript_adapter="fixture-transcriber",
        transcript_model_version="deterministic-transcript-v1",
        analysis_adapter="fixture-analyzer",
        analysis_model_version="deterministic-analysis-v1",
        prompt_version="facts-first-prompt-v1",
        playbook_version="synthetic-draft-v1",
        adapter_version="fixture-analyzer-v1",
        generated_at=event.received_at,
        processing_attempt_id="attempt-fixture-001",
        environment="fixture",
    )
    return FixtureTranscriber(source.manifest).transcribe(
        event.call,
        fixture_id="CL-FX-001",
        call_id="0123456789abcdef0123456789abcdef",
        attempt_number=1,
        provenance=provenance,
    )


def test_routes_cannot_reintroduce_local_error_or_role_policy() -> None:
    for path in ROUTE_MODULES:
        source = path.read_text()
        assert "def _error(" not in source
        assert "DemoRole." not in source
        assert "api_error(" in source
        assert "has_permission(" in source


def test_transcript_provider_contract_is_explicit() -> None:
    payload: dict[str, Any] = _accepted_transcript().model_dump(mode="json")
    payload.pop("provider_response_version")

    with pytest.raises(ValidationError, match="provider_response_version"):
        Transcript.model_validate(payload)


def test_removed_fallbacks_and_wrappers_stay_removed() -> None:
    contract_source = (ROOT / "packages/contracts/review.py").read_text()
    operations_source = (ROOT / "packages/database/local_operations.py").read_text()
    generated_schema = (ROOT / "packages/contracts/schemas/transcript.schema.json").read_text()

    assert "legacy-review-contract-v1" not in contract_source
    assert "legacy-review-contract-v1" not in generated_schema
    assert "def default_configuration(" not in operations_source


def test_endpoint_policy_is_shared_with_preflight() -> None:
    from packages.config.endpoints import safe_endpoint_class
    from packages.transcription.live import safe_endpoint_class as preflight_policy

    assert preflight_policy is safe_endpoint_class
    assert "def _safe_openai_base_url" not in (ROOT / "packages/config/settings.py").read_text()


def test_removed_live_execution_stays_removed() -> None:
    source = (ROOT / "packages/transcription/openai_adapter.py").read_text()
    assert "def _build_live_client" not in source
    assert "OpenAI(" not in source
    assert not (ROOT / "scripts/test_transcription_live.py").exists()
    assert "test-transcription-live:" not in (ROOT / "Makefile").read_text()


def test_middleware_cannot_reintroduce_error_envelopes() -> None:
    for name in ("app.py", "body_limits.py"):
        source = (ROOT / "apps/api/colacci_api" / name).read_text()
        assert '"error":' not in source


def test_routes_and_responses_share_error_detail(monkeypatch) -> None:
    import json

    from starlette.requests import Request

    from apps.api.colacci_api import errors

    calls = []

    def detail(message, correlation):
        calls.append((message, correlation))
        return {"error": message, "correlation_id": correlation}

    monkeypatch.setattr(errors, "error_detail", detail)
    request = Request({"type": "http", "state": {"correlation_id": "corr-test"}})
    raised = errors.api_error(request, 403, "forbidden")
    response = errors.error_response(403, "forbidden", "corr-test")
    assert json.loads(response.body)["detail"] == raised.detail
    assert calls == [("forbidden", "corr-test"), ("forbidden", "corr-test")]
