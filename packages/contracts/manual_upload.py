"""Strict, content-free contracts for the local synthetic upload bridge."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from packages.contracts.report import DemoPrincipalId, DemoRole
from packages.contracts.review import Direction, StrictModel

UPLOAD_SCHEMA_VERSION: Literal["manual-upload-v1"] = "manual-upload-v1"
UploadId = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{32}$")]
ClientSubmissionId = Annotated[
    str,
    StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,63}$"),
]
SafeCode = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{2,63}$")]
HashReference = Annotated[str, StringConstraints(pattern=r"^sha256:[a-f0-9]{12}$")]
SyntheticExtension = Annotated[str, StringConstraints(pattern=r"^SYN-[0-9]{3}$")]


class UploadKind(StrEnum):
    SYNTHETIC_AUDIO = "synthetic_audio"
    TRANSCRIPT_ONLY = "transcript_only"


class UploadState(StrEnum):
    RECEIVED = "received"
    VALIDATING = "validating"
    READY = "ready"
    PROCESSING = "processing"
    ANALYZED = "analyzed"
    VALIDATION_FAILED = "validation_failed"
    TRANSCRIPTION_FAILED = "transcription_failed"
    ANALYSIS_FAILED = "analysis_failed"
    CANCELLED = "cancelled"
    DELETION_FAILED = "deletion_failed"


class DeterministicOutcome(StrEnum):
    SUCCESS = "success"
    TRANSCRIPTION_RETRYABLE_ONCE = "transcription_retryable_once"
    TRANSCRIPTION_TERMINAL = "transcription_terminal"
    ANALYSIS_RETRYABLE_ONCE = "analysis_retryable_once"
    ANALYSIS_TERMINAL = "analysis_terminal"


class UploadMetadata(StrictModel):
    client_submission_id: ClientSubmissionId
    generated_only_attestation: Literal[True]
    direction: Direction
    captured_at: AwareDatetime
    language_hint: Literal["en", "es"]
    staff_extension: SyntheticExtension


class UploadValidationSummary(StrictModel):
    kind: UploadKind
    contract_version: str
    byte_size: Annotated[int, Field(gt=0)]
    duration_seconds: Annotated[float, Field(gt=0)]
    media_format: str | None = None
    channel_count: Annotated[int, Field(ge=1, le=2)] | None = None
    sample_rate_hz: Annotated[int, Field(ge=8000, le=48000)] | None = None
    segment_count: Annotated[int, Field(ge=1)] | None = None

    @model_validator(mode="after")
    def shape_matches_kind(self) -> UploadValidationSummary:
        if self.kind is UploadKind.SYNTHETIC_AUDIO:
            if (
                self.media_format is None
                or self.channel_count is None
                or self.sample_rate_hz is None
                or self.segment_count is not None
            ):
                raise ValueError("audio validation summary is incomplete")
        elif (
            self.segment_count is None
            or self.media_format is not None
            or self.channel_count is not None
            or self.sample_rate_hz is not None
        ):
            raise ValueError("transcript validation summary is incomplete")
        return self


class UploadStateEvent(StrictModel):
    event_id: UploadId
    state: UploadState
    attempt_number: Annotated[int, Field(ge=0, le=3)]
    diagnostic_code: SafeCode | None = None
    occurred_at: AwareDatetime


class UploadReceipt(StrictModel):
    schema_version: Literal["manual-upload-v1"] = UPLOAD_SCHEMA_VERSION
    upload_id: UploadId
    source_event_id: str
    call_id: UploadId | None = None
    submission_kind: UploadKind
    synthetic: Literal[True] = True
    content_hash_reference: HashReference
    language_hint: Literal["en", "es"]
    direction: Direction
    captured_at: AwareDatetime
    staff_extension: SyntheticExtension
    principal_id: DemoPrincipalId
    role: DemoRole
    state: UploadState
    attempt_number: Annotated[int, Field(ge=0, le=3)]
    diagnostic_code: SafeCode | None = None
    retryable: bool
    deletion_confirmed: bool | None = None
    validation: UploadValidationSummary
    created_at: AwareDatetime
    updated_at: AwareDatetime
    cancelled_at: AwareDatetime | None = None
    deleted_at: AwareDatetime | None = None
    duplicate: bool = False
    call_path: str | None = None
    report_path: str | None = None
    history: tuple[UploadStateEvent, ...] = ()

    @model_validator(mode="after")
    def terminal_metadata_is_consistent(self) -> UploadReceipt:
        if self.state is UploadState.ANALYZED and self.call_id is None:
            raise ValueError("analyzed receipts require a call")
        if self.state is UploadState.CANCELLED and self.cancelled_at is None:
            raise ValueError("cancelled receipts require a cancellation timestamp")
        if self.call_path is not None and self.call_id is None:
            raise ValueError("call links require a call")
        return self


class UploadList(StrictModel):
    uploads: tuple[UploadReceipt, ...]


class UploadCapabilities(StrictModel):
    principal_id: DemoPrincipalId
    role: DemoRole
    can_open_completed: bool
    can_append_feedback: bool
    can_submit: bool
    can_view_receipts: bool
    can_retry: bool
    can_cancel: bool
    can_publish_playbook: bool


class SyntheticManifestEntry(StrictModel):
    content_sha256: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
    fixture_id: Literal["CL-FX-002", "CL-FX-003"]
    outcome: DeterministicOutcome = DeterministicOutcome.SUCCESS


class SyntheticUploadManifest(StrictModel):
    manifest_version: Literal["manual-upload-synthetic-manifest-v1"]
    generated_only: Literal[True]
    entries: tuple[SyntheticManifestEntry, ...]

    @model_validator(mode="after")
    def fingerprints_are_unique(self) -> SyntheticUploadManifest:
        values = [entry.content_sha256 for entry in self.entries]
        if not values or len(values) != len(set(values)):
            raise ValueError("synthetic upload fingerprints must be nonempty and unique")
        return self
