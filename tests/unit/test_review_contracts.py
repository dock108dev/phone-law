from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from packages.contracts.review import (
    SCHEMA_VERSION,
    AnalysisAcceptanceState,
    DateFact,
    EvidenceReference,
    Finding,
    IdentityClaim,
    NormalizedCall,
    Priority,
    ProcessingState,
    Provenance,
    Speaker,
    StructuredAnalysis,
    ValueState,
)
from packages.review.fixtures import (
    FixtureAdapterError,
    FixtureAnalyzer,
    FixtureCallSource,
    FixtureTranscriber,
)
from packages.review.state_machine import (
    InvalidStateTransitionError,
    start_explicit_retry,
    transition,
)
from packages.review.validation import (
    ReviewValidationError,
    acceptance_state_for,
    validate_analysis,
    validate_evidence,
)
from scripts.generate_contract_schemas import MODELS, rendered_schema


def provenance(fixture_id: str) -> Provenance:
    event = FixtureCallSource().events(fixture_id)[0]
    return Provenance.model_validate_json(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "call_source": "fixture",
                "source_event_id": event.call.source_event_id,
                "source_call_id": event.call.source_call_id,
                "transcript_adapter": "fixture-transcriber",
                "transcript_model_version": "deterministic-transcript-v1",
                "analysis_adapter": "fixture-analyzer",
                "analysis_model_version": "deterministic-analysis-v1",
                "prompt_version": "facts-first-prompt-v1",
                "playbook_version": "synthetic-draft-v1",
                "adapter_version": "fixture-analyzer-v1",
                "generated_at": "2026-08-17T20:00:00Z",
                "processing_attempt_id": "attempt-fixture-001",
                "environment": "fixture",
            }
        )
    )


def accepted_fixture(
    fixture_id: str = "CL-FX-001",
) -> tuple[NormalizedCall, Any, StructuredAnalysis]:
    source = FixtureCallSource()
    event = source.events(fixture_id)[0]
    transcript = FixtureTranscriber(source.manifest).transcribe(
        event.call,
        fixture_id=fixture_id,
        call_id="0123456789abcdef0123456789abcdef",
        attempt_number=1,
        provenance=provenance(fixture_id),
    )
    analyzer = FixtureAnalyzer(source.manifest)
    facts = analyzer.extract_facts(fixture_id, transcript)
    analysis = analyzer.apply_playbook(
        fixture_id,
        call_id=transcript.call_id,
        facts=facts,
        transcript=transcript,
        provenance=transcript.provenance,
    )
    return event.call, transcript, analysis


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("occurred_at", "not-rfc3339"),
        ("duration_seconds", -1.0),
        ("language_hint", "fr"),
        ("direction", "sideways"),
        ("source", "guessed_provider"),
    ],
)
def test_normalized_call_rejects_invalid_contract_values(field: str, value: object) -> None:
    payload = FixtureCallSource().events("CL-FX-001")[0].call.model_dump(mode="json")
    payload[field] = value
    with pytest.raises(ValidationError):
        NormalizedCall.model_validate_json(json.dumps(payload))


def test_normalized_call_rejects_extra_fields_provider_data_and_non_synthetic_fixture() -> None:
    payload = FixtureCallSource().events("CL-FX-001")[0].call.model_dump(mode="json")
    payload["unexpected"] = True
    with pytest.raises(ValidationError, match="extra_forbidden"):
        NormalizedCall.model_validate_json(json.dumps(payload))
    payload.pop("unexpected")
    payload["metadata"] = {"provider_url": "opaque"}
    with pytest.raises(ValidationError, match="provider or caller data"):
        NormalizedCall.model_validate_json(json.dumps(payload))
    payload["metadata"] = {}
    payload["synthetic"] = False
    with pytest.raises(ValidationError, match="marked synthetic"):
        NormalizedCall.model_validate_json(json.dumps(payload))


def test_evidence_validation_accepts_fixture_and_rejects_invalid_references() -> None:
    call, transcript, analysis = accepted_fixture()
    validate_analysis(analysis, transcript, call.duration_seconds)
    reference = analysis.findings[0].evidence[0]

    with pytest.raises(ValidationError):
        EvidenceReference.model_validate({**reference.model_dump(), "start_seconds": -0.1})
    with pytest.raises(ValidationError):
        EvidenceReference.model_validate(
            {**reference.model_dump(), "start_seconds": reference.end_seconds}
        )

    cases = (
        (
            reference.model_copy(update={"segment_id": "missing-segment"}),
            call.duration_seconds,
            "evidence_segment_not_found",
        ),
        (
            reference.model_copy(update={"speaker": Speaker.STAFF}),
            call.duration_seconds,
            "evidence_speaker_mismatch",
        ),
        (
            reference.model_copy(update={"excerpt": "unsupported excerpt"}),
            call.duration_seconds,
            "evidence_excerpt_unsupported",
        ),
        (reference, reference.end_seconds - 0.1, "evidence_outside_call_duration"),
    )
    for invalid, duration, code in cases:
        with pytest.raises(ReviewValidationError, match=code):
            validate_evidence(invalid, transcript, duration)


def test_strict_analysis_rejects_role_enum_malformed_output_and_extra_fields() -> None:
    _, _, analysis = accepted_fixture()
    payload = analysis.model_dump(mode="json")
    payload["responsible_role"] = "fictional_real_person"
    with pytest.raises(ValidationError):
        StructuredAnalysis.model_validate_json(json.dumps(payload))
    payload["responsible_role"] = "intake_team"
    payload["extra_claim"] = "not allowed"
    with pytest.raises(ValidationError, match="extra_forbidden"):
        StructuredAnalysis.model_validate_json(json.dumps(payload))
    del payload["extra_claim"]
    del payload["summary"]
    with pytest.raises(ValidationError, match="Field required"):
        StructuredAnalysis.model_validate_json(json.dumps(payload))


def test_unsupported_high_priority_finding_cannot_be_accepted() -> None:
    call, transcript, analysis = accepted_fixture()
    unsupported = Finding(
        finding_id="unsupported-finding",
        kind="unsupported_priority",
        statement="Unsupported priority claim.",
        material=True,
        evidence=(),
    )
    candidate = analysis.model_copy(update={"priority": Priority.HIGH, "findings": (unsupported,)})
    with pytest.raises(ReviewValidationError, match="material_finding_missing_evidence"):
        validate_analysis(candidate, transcript, call.duration_seconds)
    assert (
        acceptance_state_for(candidate, transcript, call.duration_seconds)
        is AnalysisAcceptanceState.NEEDS_REVIEW
    )
    review_candidate = candidate.model_copy(
        update={"acceptance_state": AnalysisAcceptanceState.NEEDS_REVIEW}
    )
    with pytest.raises(ReviewValidationError):
        validate_analysis(review_candidate, transcript, call.duration_seconds)


def test_invented_deadline_and_verified_identity_without_metadata_are_rejected() -> None:
    with pytest.raises(ValidationError, match="deadline must be confirmed"):
        DateFact(
            state=ValueState.UNVERIFIED,
            expression="maybe Friday",
            iso_date=None,
            is_deadline=True,
            evidence=(),
        )
    with pytest.raises(ValidationError, match="supporting metadata"):
        IdentityClaim(
            state=ValueState.PRESENT,
            label="Asserted caller",
            metadata_verified=False,
        )

    call, transcript, analysis = accepted_fixture()
    identity = IdentityClaim(
        state=ValueState.PRESENT,
        label="Metadata-asserted identity",
        metadata_verified=True,
    )
    candidate = analysis.model_copy(
        update={"facts": analysis.facts.model_copy(update={"caller_identity": identity})}
    )
    with pytest.raises(ReviewValidationError, match="verified_caller_identity_missing_metadata"):
        validate_analysis(candidate, transcript, call.duration_seconds)


def test_generated_contract_schemas_are_synchronized() -> None:
    schema_directory = Path("packages/contracts/schemas")
    for filename, model in MODELS.items():
        assert (schema_directory / filename).read_text(encoding="utf-8") == rendered_schema(model)


def test_state_machine_allows_only_explicit_sequence_and_retry() -> None:
    state = ProcessingState.RECEIVED
    for target in (
        ProcessingState.VALIDATED,
        ProcessingState.QUEUED,
        ProcessingState.MEDIA_READY,
        ProcessingState.TRANSCRIBING,
        ProcessingState.TRANSCRIBED,
        ProcessingState.EXTRACTING_FACTS,
        ProcessingState.APPLYING_PLAYBOOK,
        ProcessingState.ANALYZED,
    ):
        state = transition(state, target)
    with pytest.raises(InvalidStateTransitionError):
        transition(state, ProcessingState.RECEIVED)
    assert start_explicit_retry(ProcessingState.TRANSCRIPTION_FAILED) is ProcessingState.RECEIVED
    with pytest.raises(InvalidStateTransitionError):
        start_explicit_retry(ProcessingState.AUDIO_INVALID)


def test_fixture_specific_contracts_preserve_language_ambiguity_and_uncertainty() -> None:
    _, _, commitment_analysis = accepted_fixture("CL-FX-002")
    commitment = commitment_analysis.facts.staff_commitments[0]
    assert commitment.evidence[0].speaker is Speaker.STAFF
    assert commitment.evidence[0].segment_id == "fx002-seg-4"

    _, spanish_transcript, spanish_analysis = accepted_fixture("CL-FX-003")
    assert spanish_transcript.language == "es"
    assert spanish_transcript.segments[0].text.startswith("Hola.")
    assert spanish_analysis.suggested_response_timing is None

    _, ambiguous_transcript, _ = accepted_fixture("CL-FX-007")
    assert any(
        segment.speaker is Speaker.UNKNOWN_PARTICIPANT for segment in ambiguous_transcript.segments
    )

    _, _, injection_analysis = accepted_fixture("CL-FX-008")
    assert injection_analysis.priority is Priority.LOW

    _, _, dates_analysis = accepted_fixture("CL-FX-012")
    assert all(
        item.state is ValueState.UNVERIFIED and not item.is_deadline
        for item in dates_analysis.facts.dates
    )


def test_fixture_transcriber_emits_only_sanitized_retry_failure() -> None:
    source = FixtureCallSource()
    event = source.events("CL-FX-010")[0]
    with pytest.raises(FixtureAdapterError) as captured:
        FixtureTranscriber(source.manifest).transcribe(
            event.call,
            fixture_id="CL-FX-010",
            call_id="0123456789abcdef0123456789abcdef",
            attempt_number=1,
            provenance=provenance("CL-FX-010"),
        )
    assert captured.value.retryable is True
    assert captured.value.diagnostic_code == "fixture_transcriber_retryable"
