"""Strict media and transcription-boundary contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from packages.contracts.review import OpaqueId, StrictModel

MEDIA_SCHEMA_VERSION: Literal["media-contracts-v1"] = "media-contracts-v1"
Sha256Digest = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
HashReference = Annotated[str, StringConstraints(pattern=r"^sha256:[a-f0-9]{12}$")]


class SupportedMediaFormat(StrEnum):
    MP3 = "mp3"
    MP4 = "mp4"
    MPEG = "mpeg"
    MPGA = "mpga"
    M4A = "m4a"
    WAV = "wav"
    WEBM = "webm"


class MediaContentType(StrEnum):
    AUDIO_MPEG = "audio/mpeg"
    AUDIO_MP4 = "audio/mp4"
    AUDIO_WAV = "audio/wav"
    AUDIO_WEBM = "audio/webm"
    VIDEO_MP4 = "video/mp4"


class MediaLifecycleState(StrEnum):
    RECEIVED = "RECEIVED"
    INSPECTED = "INSPECTED"
    NORMALIZED = "NORMALIZED"
    TRANSCRIBING = "TRANSCRIBING"
    TRANSCRIBED = "TRANSCRIBED"
    DELETED = "DELETED"


class MediaErrorClass(StrEnum):
    EMPTY_MEDIA = "EMPTY_MEDIA"
    UNSUPPORTED_MEDIA = "UNSUPPORTED_MEDIA"
    CORRUPT_MEDIA = "CORRUPT_MEDIA"
    OVERSIZED_MEDIA = "OVERSIZED_MEDIA"
    OVERLONG_MEDIA = "OVERLONG_MEDIA"
    NORMALIZATION_FAILED = "NORMALIZATION_FAILED"
    TRANSCRIPTION_TIMEOUT = "TRANSCRIPTION_TIMEOUT"
    TRANSCRIPTION_RATE_LIMITED = "TRANSCRIPTION_RATE_LIMITED"
    TRANSCRIPTION_AUTH_FAILED = "TRANSCRIPTION_AUTH_FAILED"
    TRANSCRIPTION_PROVIDER_FAILED = "TRANSCRIPTION_PROVIDER_FAILED"
    TRANSCRIPTION_RESPONSE_INVALID = "TRANSCRIPTION_RESPONSE_INVALID"
    TRANSCRIPTION_CANCELLED = "TRANSCRIPTION_CANCELLED"
    MEDIA_DELETION_FAILED = "MEDIA_DELETION_FAILED"


class TimestampAvailability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class DiarizationAvailability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class MediaInput(StrictModel):
    schema_version: Literal["media-contracts-v1"] = MEDIA_SCHEMA_VERSION
    artifact_id: OpaqueId
    synthetic: Literal[True]
    declared_content_type: MediaContentType | None = None
    declared_byte_size: Annotated[int, Field(ge=0)]


class MediaInspectionResult(StrictModel):
    schema_version: Literal["media-contracts-v1"] = MEDIA_SCHEMA_VERSION
    artifact_id: OpaqueId
    synthetic: Literal[True]
    media_format: SupportedMediaFormat
    content_type: MediaContentType
    byte_size: Annotated[int, Field(gt=0)]
    duration_seconds: Annotated[float, Field(gt=0)]
    sample_rate_hz: Annotated[int, Field(gt=0)]
    channel_count: Annotated[int, Field(ge=1, le=8)]
    codec: OpaqueId
    content_sha256: Sha256Digest
    inspected_at: AwareDatetime

    @property
    def hash_reference(self) -> str:
        return f"sha256:{self.content_sha256[:12]}"


class TemporaryObjectReference(StrictModel):
    schema_version: Literal["media-contracts-v1"] = MEDIA_SCHEMA_VERSION
    object_id: OpaqueId
    artifact_id: OpaqueId
    store_name: Literal["local-synthetic-v1"]
    synthetic: Literal[True]
    created_at: AwareDatetime


class NormalizationResult(StrictModel):
    schema_version: Literal["media-contracts-v1"] = MEDIA_SCHEMA_VERSION
    artifact_id: OpaqueId
    source_object_id: OpaqueId
    normalized_object_id: OpaqueId
    normalized: bool
    media_format: SupportedMediaFormat
    byte_size: Annotated[int, Field(gt=0)]
    duration_seconds: Annotated[float, Field(gt=0)]
    sample_rate_hz: Annotated[int, Field(gt=0)]
    channel_count: Annotated[int, Field(ge=1, le=8)]
    content_sha256: Sha256Digest


class MediaLifecycleEvent(StrictModel):
    schema_version: Literal["media-contracts-v1"] = MEDIA_SCHEMA_VERSION
    event_id: OpaqueId
    artifact_id: OpaqueId
    state: MediaLifecycleState
    occurred_at: AwareDatetime
    synthetic: Literal[True]


class MediaDeletionEvent(StrictModel):
    schema_version: Literal["media-contracts-v1"] = MEDIA_SCHEMA_VERSION
    event_id: OpaqueId
    artifact_id: OpaqueId
    object_id: OpaqueId
    state: Literal[MediaLifecycleState.DELETED]
    deletion_confirmed: bool
    error_class: Literal[MediaErrorClass.MEDIA_DELETION_FAILED] | None = None
    occurred_at: AwareDatetime

    @model_validator(mode="after")
    def failure_is_visible(self) -> MediaDeletionEvent:
        if self.deletion_confirmed == (self.error_class is not None):
            raise ValueError("deletion confirmation and error classification are inconsistent")
        return self


class ProviderSpeakerLabel(StrictModel):
    raw_label: OpaqueId
    mapped_participant: Literal["unknown_participant"] = "unknown_participant"
    identity_verified: Literal[False] = False


class TranscriptionUsageMetadata(StrictModel):
    input_tokens: Annotated[int, Field(ge=0)] | None = None
    output_tokens: Annotated[int, Field(ge=0)] | None = None
    duration_seconds: Annotated[float, Field(ge=0)] | None = None


class TranscriptionRequestMetadata(StrictModel):
    schema_version: Literal["media-contracts-v1"] = MEDIA_SCHEMA_VERSION
    call_id: OpaqueId
    attempt_number: Annotated[int, Field(ge=1, le=3)]
    artifact_id: OpaqueId
    media_hash_reference: HashReference
    adapter_version: OpaqueId
    model_id: OpaqueId
    fallback_model_id: OpaqueId
    response_format: Literal["diarized_json"]
    chunking_strategy: Literal["auto"] | None
    timeout_seconds: Annotated[float, Field(gt=0, le=120)]
    byte_size: Annotated[int, Field(gt=0)]
    duration_seconds: Annotated[float, Field(gt=0)]


class TranscriptionResponseMetadata(StrictModel):
    schema_version: Literal["media-contracts-v1"] = MEDIA_SCHEMA_VERSION
    call_id: OpaqueId
    attempt_number: Annotated[int, Field(ge=1, le=3)]
    model_id: OpaqueId
    provider_response_version: OpaqueId
    language: Literal["en", "es"]
    timestamp_availability: TimestampAvailability
    diarization_availability: DiarizationAvailability
    speaker_labels: tuple[ProviderSpeakerLabel, ...] = ()
    usage: TranscriptionUsageMetadata | None = None


class TranscriptionErrorClassification(StrictModel):
    schema_version: Literal["media-contracts-v1"] = MEDIA_SCHEMA_VERSION
    error_class: MediaErrorClass
    retryable: bool
    attempt_number: Annotated[int, Field(ge=1, le=3)]
    retry_after_seconds: Annotated[float, Field(ge=0, le=30)] | None = None
