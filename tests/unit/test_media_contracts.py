from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from packages.config import AppProfile, Settings
from packages.contracts.media import (
    MediaContentType,
    MediaDeletionEvent,
    MediaErrorClass,
    MediaInspectionResult,
    MediaLifecycleState,
    SupportedMediaFormat,
)
from packages.contracts.review import (
    CallSource,
    DiarizationStatus,
    Provenance,
    TimestampAvailability,
    Transcript,
    TranscriptValidationState,
)
from packages.review.fixtures import FixtureAnalyzer, FixtureCallSource, FixtureTranscriber
from packages.review.validation import (
    ReviewValidationError,
    transcript_validation_state,
    validate_analysis,
)
from packages.transcription import LiveTranscriptionBlockedError, create_live_openai_transcriber


def provenance(fixture_id: str) -> Provenance:
    event = FixtureCallSource().events(fixture_id)[0]
    return Provenance(
        schema_version="review-contracts-v1",
        call_source=CallSource.FIXTURE,
        source_event_id=event.call.source_event_id,
        source_call_id=event.call.source_call_id,
        transcript_adapter="fixture-transcriber",
        transcript_model_version="deterministic-transcript-v1",
        analysis_adapter="fixture-analyzer",
        analysis_model_version="deterministic-analysis-v1",
        prompt_version="facts-first-prompt-v1",
        playbook_version="synthetic-draft-v1",
        adapter_version="fixture-analyzer-v1",
        generated_at=datetime.now(UTC),
        processing_attempt_id="attempt-fixture-001",
        environment="fixture",
    )


def test_media_contract_enforces_hash_size_and_deletion_consistency() -> None:
    inspection = MediaInspectionResult(
        artifact_id="0123456789abcdef0123456789abcdef",
        synthetic=True,
        media_format=SupportedMediaFormat.WAV,
        content_type=MediaContentType.AUDIO_WAV,
        byte_size=44,
        duration_seconds=1,
        sample_rate_hz=16000,
        channel_count=1,
        codec="pcm_s16le",
        content_sha256="a" * 64,
        inspected_at=datetime.now(UTC),
    )
    assert inspection.hash_reference == "sha256:aaaaaaaaaaaa"
    with pytest.raises(ValidationError):
        MediaInspectionResult.model_validate({**inspection.model_dump(), "channel_count": 0})
    with pytest.raises(ValidationError, match="inconsistent"):
        MediaDeletionEvent(
            event_id="1123456789abcdef0123456789abcdef",
            artifact_id=inspection.artifact_id,
            object_id="2123456789abcdef0123456789abcdef",
            state=MediaLifecycleState.DELETED,
            deletion_confirmed=True,
            error_class=MediaErrorClass.MEDIA_DELETION_FAILED,
            occurred_at=datetime.now(UTC),
        )


def test_timestamp_free_transcript_requires_visible_review_and_blocks_analysis() -> None:
    source = FixtureCallSource()
    event = source.events("CL-FX-001")[0]
    accepted_transcript = FixtureTranscriber(source.manifest).transcribe(
        event.call,
        fixture_id="CL-FX-001",
        call_id="0123456789abcdef0123456789abcdef",
        attempt_number=1,
        provenance=provenance("CL-FX-001"),
    )
    analyzer = FixtureAnalyzer(source.manifest)
    facts = analyzer.extract_facts("CL-FX-001", accepted_transcript)
    analysis = analyzer.apply_playbook(
        "CL-FX-001",
        call_id=accepted_transcript.call_id,
        facts=facts,
        transcript=accepted_transcript,
        provenance=accepted_transcript.provenance,
    )
    fallback = Transcript(
        transcript_id="0123456789abcdef0123456789abcdef",
        call_id=accepted_transcript.call_id,
        language="en",
        diarization_status=DiarizationStatus.UNAVAILABLE,
        original_language_text="Invented fallback text remains available for review.",
        timestamp_availability=TimestampAvailability.UNAVAILABLE,
        provider_response_version="invented-fallback-v1",
        media_hash_reference="sha256:aaaaaaaaaaaa",
        validation_state=TranscriptValidationState.REQUIRES_HUMAN_REVIEW,
        segments=(),
        provenance=accepted_transcript.provenance,
    )
    assert transcript_validation_state(fallback) is TranscriptValidationState.REQUIRES_HUMAN_REVIEW
    with pytest.raises(ReviewValidationError, match="timestamps_unavailable"):
        validate_analysis(analysis, fallback, event.call.duration_seconds)
    with pytest.raises(ValidationError, match="require visible human review"):
        Transcript(
            **{
                **fallback.model_dump(),
                "validation_state": TranscriptValidationState.ACCEPTED,
            }
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"live_transcription_enabled": True},
        {"live_transcription_authorized": True},
        {"transcription_approval_reference": "approval-should-not-enable-slice3a"},
        {"media_max_bytes": 25 * 1024 * 1024 + 1},
        {"media_temp_root": "/var/tmp/outside-boundary"},
    ],
)
def test_slice3a_configuration_rejects_live_or_unsafe_media_settings(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_profile=AppProfile.TEST, **overrides)


def test_live_factory_remains_blocked_with_safe_defaults() -> None:
    settings = Settings(_env_file=None, app_profile=AppProfile.TEST)
    with pytest.raises(LiveTranscriptionBlockedError, match="slice3b"):
        create_live_openai_transcriber(settings)
