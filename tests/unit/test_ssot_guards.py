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
