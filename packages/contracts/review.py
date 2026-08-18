"""Strict, versioned contracts for the synthetic review pipeline."""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

SCHEMA_VERSION = "review-contracts-v1"
OpaqueId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")]
NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
CurrencyCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class CallSource(StrEnum):
    FIXTURE = "fixture"
    TRANSCRIPT_ONLY = "transcript_only"
    MANUAL_UPLOAD = "manual_upload"
    BROADVOICE = "broadvoice"


class Direction(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    UNKNOWN = "unknown"


class Speaker(StrEnum):
    STAFF = "staff"
    OUTSIDE_CALLER = "outside_caller"
    UNKNOWN_PARTICIPANT = "unknown_participant"


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AnalysisCategory(StrEnum):
    NEW_INTAKE = "new_intake"
    EXISTING_CLIENT_FOLLOW_UP = "existing_client_follow_up"
    ADMINISTRATIVE = "administrative"
    DISSATISFACTION_ESCALATION = "dissatisfaction_escalation"
    ROUTINE_NO_ACTION = "routine_no_action"
    UNKNOWN = "unknown"


class Priority(StrEnum):
    IMMEDIATE = "immediate"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class ValueState(StrEnum):
    PRESENT = "present"
    MISSING = "missing"
    UNKNOWN = "unknown"
    UNVERIFIED = "unverified"
    NOT_MENTIONED = "not_mentioned"


class IngestionDisposition(StrEnum):
    ACCEPTED = "accepted"
    DUPLICATE_EVENT = "duplicate_event"
    DUPLICATE_CALL = "duplicate_call"


class ProcessingState(StrEnum):
    RECEIVED = "RECEIVED"
    VALIDATED = "VALIDATED"
    QUEUED = "QUEUED"
    MEDIA_READY = "MEDIA_READY"
    TRANSCRIBING = "TRANSCRIBING"
    TRANSCRIBED = "TRANSCRIBED"
    EXTRACTING_FACTS = "EXTRACTING_FACTS"
    APPLYING_PLAYBOOK = "APPLYING_PLAYBOOK"
    ANALYZED = "ANALYZED"
    AUDIO_INVALID = "AUDIO_INVALID"
    TRANSCRIPTION_FAILED = "TRANSCRIPTION_FAILED"
    OUTPUT_VALIDATION_FAILED = "OUTPUT_VALIDATION_FAILED"
    ANALYSIS_FAILED = "ANALYSIS_FAILED"


class AnalysisAcceptanceState(StrEnum):
    ACCEPTED = "accepted"
    NEEDS_REVIEW = "needs_review"
    REJECTED = "rejected"


class AdvisoryStatus(StrEnum):
    ADVISORY = "advisory"


class PlaybookStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    RETIRED = "retired"


class DiarizationStatus(StrEnum):
    AVAILABLE = "available"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class TimestampAvailability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class TranscriptValidationState(StrEnum):
    ACCEPTED = "accepted"
    REQUIRES_HUMAN_REVIEW = "requires_human_review"
    REJECTED = "rejected"


class FailureClass(StrEnum):
    INVALID_MEDIA = "invalid_media"
    TRANSCRIBER_UNAVAILABLE = "transcriber_unavailable"
    INVALID_STRUCTURED_OUTPUT = "invalid_structured_output"
    ANALYZER_UNAVAILABLE = "analyzer_unavailable"


class ResponsibleRole(StrEnum):
    INTAKE_TEAM = "intake_team"
    CASE_TEAM = "case_team"
    RECORDS_COORDINATOR = "records_coordinator"
    SUPERVISING_ATTORNEY = "supervising_attorney"
    SPANISH_SPEAKING_INTAKE = "spanish_speaking_intake"
    UNASSIGNED = "unassigned"


class NormalizedCall(StrictModel):
    source: CallSource
    source_event_id: OpaqueId
    source_call_id: OpaqueId
    recording_id: OpaqueId | None = None
    occurred_at: AwareDatetime
    direction: Direction
    duration_seconds: Annotated[float, Field(ge=0)]
    staff_extension: OpaqueId | None = None
    language_hint: Literal["en", "es"] | None = None
    media_reference: OpaqueId | None = None
    transcript_fixture_reference: OpaqueId | None = None
    metadata: dict[str, bool | int | float | str | None] = Field(default_factory=dict)
    synthetic: bool

    @model_validator(mode="after")
    def enforce_source_boundary(self) -> NormalizedCall:
        if self.source in {CallSource.FIXTURE, CallSource.TRANSCRIPT_ONLY} and not self.synthetic:
            raise ValueError("local synthetic sources must be marked synthetic")
        if self.source is CallSource.TRANSCRIPT_ONLY:
            if self.media_reference is not None or self.transcript_fixture_reference is None:
                raise ValueError("transcript-only calls require only a transcript reference")
            if self.metadata.get("source_mode") != "transcript_only":
                raise ValueError("transcript-only calls require the explicit source label")
        forbidden = {
            "access_token",
            "authorization",
            "caller_name",
            "phone_number",
            "provider_credentials",
            "provider_url",
        }
        if forbidden.intersection(key.lower() for key in self.metadata):
            raise ValueError("provider or caller data is forbidden in normalized metadata")
        for reference in (self.media_reference, self.transcript_fixture_reference):
            if reference and re.search(r"(?:https?|postgres(?:ql)?):", reference, re.IGNORECASE):
                raise ValueError("references must be opaque internal identifiers")
        return self


class IngestionEvent(StrictModel):
    fixture_id: OpaqueId
    received_at: AwareDatetime
    call: NormalizedCall


class IngestionResult(StrictModel):
    call_id: OpaqueId
    event_id: OpaqueId
    disposition: IngestionDisposition


class SpeakerIdentity(StrictModel):
    speaker: Speaker
    asserted_label: NonEmptyText | None = None
    verification_state: Literal[ValueState.UNKNOWN, ValueState.UNVERIFIED]
    raw_provider_speaker_label: OpaqueId | None = None


class EvidenceReference(StrictModel):
    segment_id: OpaqueId
    start_seconds: Annotated[float, Field(ge=0)]
    end_seconds: Annotated[float, Field(gt=0)]
    speaker: Speaker
    excerpt: NonEmptyText

    @model_validator(mode="after")
    def start_precedes_end(self) -> EvidenceReference:
        if self.start_seconds >= self.end_seconds:
            raise ValueError("evidence start must precede end")
        return self


class TranscriptSegment(StrictModel):
    segment_id: OpaqueId
    speaker: Speaker
    identity: SpeakerIdentity
    start_seconds: Annotated[float, Field(ge=0)] | None
    end_seconds: Annotated[float, Field(gt=0)] | None
    text: NonEmptyText

    @model_validator(mode="after")
    def segment_is_ordered(self) -> TranscriptSegment:
        if (self.start_seconds is None) != (self.end_seconds is None):
            raise ValueError("segment timestamps must be both present or both unavailable")
        if (
            self.start_seconds is not None
            and self.end_seconds is not None
            and self.start_seconds >= self.end_seconds
        ):
            raise ValueError("segment start must precede end")
        if self.identity.speaker is not self.speaker:
            raise ValueError("speaker identity must match segment speaker")
        return self


class TranscriptionTransportProvenance(StrictModel):
    transport: Literal["fixture", "openai_cli_local", "sdk", "transcript_only"]
    declared_contract_version: OpaqueId
    observed_cli_version: OpaqueId | Literal["unavailable"]
    model_id: OpaqueId
    requested_response_format: OpaqueId
    generated_asset_fingerprint: (
        Annotated[str, StringConstraints(pattern=r"^sha256:[a-f0-9]{12}$")] | None
    ) = None
    attempt_number: Annotated[int, Field(ge=1, le=3)]
    result_kind: Literal["deterministic_fixture", "separately_authorized_live", "transcript_only"]


class Provenance(StrictModel):
    schema_version: Literal["review-contracts-v1"]
    call_source: CallSource
    source_event_id: OpaqueId
    source_call_id: OpaqueId
    transcript_adapter: OpaqueId
    transcript_model_version: OpaqueId
    analysis_adapter: OpaqueId
    analysis_model_version: OpaqueId
    prompt_version: OpaqueId
    playbook_version: OpaqueId
    adapter_version: OpaqueId
    generated_at: AwareDatetime
    processing_attempt_id: OpaqueId
    environment: Literal[
        "fixture", "demonstration", "local_dev", "live_test", "staging", "real_client"
    ]
    endpoint_class: OpaqueId | None = None
    project_configuration: OpaqueId | None = None
    authorization_reference: OpaqueId | None = None
    transcription_transport: TranscriptionTransportProvenance | None = None


class Transcript(StrictModel):
    transcript_id: OpaqueId
    call_id: OpaqueId
    language: Literal["en", "es"]
    diarization_status: DiarizationStatus
    original_language_text: NonEmptyText | None = None
    timestamp_availability: TimestampAvailability = TimestampAvailability.AVAILABLE
    provider_response_version: OpaqueId = "legacy-review-contract-v1"
    media_hash_reference: (
        Annotated[str, StringConstraints(pattern=r"^sha256:[a-f0-9]{12}$")] | None
    ) = None
    validation_state: TranscriptValidationState = TranscriptValidationState.ACCEPTED
    segments: tuple[TranscriptSegment, ...]
    provenance: Provenance

    @field_validator("segments")
    @classmethod
    def require_unique_segments(
        cls, segments: tuple[TranscriptSegment, ...]
    ) -> tuple[TranscriptSegment, ...]:
        identifiers = [item.segment_id for item in segments]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("transcript segment identifiers must be unique")
        return segments

    @model_validator(mode="after")
    def timestamps_match_availability(self) -> Transcript:
        has_timestamps = all(
            item.start_seconds is not None and item.end_seconds is not None
            for item in self.segments
        )
        if self.timestamp_availability is TimestampAvailability.AVAILABLE and (
            not self.segments or not has_timestamps
        ):
            raise ValueError("available timestamps require complete segment timestamps")
        if self.timestamp_availability is TimestampAvailability.UNAVAILABLE and any(
            item.start_seconds is not None or item.end_seconds is not None for item in self.segments
        ):
            raise ValueError("unavailable timestamps cannot carry segment timestamps")
        if (
            self.timestamp_availability is TimestampAvailability.UNAVAILABLE
            and self.validation_state is TranscriptValidationState.ACCEPTED
        ):
            raise ValueError("timestamp-free transcripts require visible human review")
        return self


class TextFact(StrictModel):
    state: ValueState
    value: NonEmptyText | None = None
    evidence: tuple[EvidenceReference, ...] = ()

    @model_validator(mode="after")
    def state_matches_value(self) -> TextFact:
        if self.state is ValueState.PRESENT and self.value is None:
            raise ValueError("present facts require a value")
        if self.state is not ValueState.PRESENT and self.value is not None:
            raise ValueError("non-present facts cannot carry a value")
        return self


class DateFact(StrictModel):
    state: ValueState
    expression: NonEmptyText | None = None
    iso_date: str | None = None
    is_deadline: bool = False
    evidence: tuple[EvidenceReference, ...] = ()

    @model_validator(mode="after")
    def validate_date_state(self) -> DateFact:
        if self.state in {ValueState.PRESENT, ValueState.UNVERIFIED} and self.expression is None:
            raise ValueError("mentioned dates require their original expression")
        if self.state not in {ValueState.PRESENT, ValueState.UNVERIFIED} and (
            self.expression is not None or self.iso_date is not None
        ):
            raise ValueError("unmentioned dates cannot carry a date")
        if self.state is ValueState.UNVERIFIED and self.iso_date is not None:
            raise ValueError("unverified dates cannot be normalized as confirmed dates")
        if self.iso_date is not None:
            datetime.strptime(self.iso_date, "%Y-%m-%d")
        if self.is_deadline and self.state is not ValueState.PRESENT:
            raise ValueError("a deadline must be confirmed before it is represented as such")
        return self


class AppointmentFact(StrictModel):
    state: ValueState
    date: DateFact | None = None
    purpose: NonEmptyText | None = None
    evidence: tuple[EvidenceReference, ...] = ()


class MonetaryFigure(StrictModel):
    state: ValueState
    amount: (
        Annotated[str, StringConstraints(pattern=r"^(0|[1-9][0-9]*)(\.[0-9]{1,2})?$")] | None
    ) = None
    currency: CurrencyCode | None = None
    evidence: tuple[EvidenceReference, ...] = ()

    @model_validator(mode="after")
    def amount_has_currency(self) -> MonetaryFigure:
        if self.state is ValueState.PRESENT and (self.amount is None or self.currency is None):
            raise ValueError("present monetary figures require amount and currency")
        if self.state is not ValueState.PRESENT and (
            self.amount is not None or self.currency is not None
        ):
            raise ValueError("non-present monetary figures cannot carry an amount")
        return self


class StaffCommitment(StrictModel):
    state: ValueState
    commitment: NonEmptyText | None = None
    responsible_role: ResponsibleRole
    timing: DateFact | None = None
    evidence: tuple[EvidenceReference, ...] = ()

    @model_validator(mode="after")
    def commitment_requires_evidence(self) -> StaffCommitment:
        if self.state is ValueState.PRESENT and (self.commitment is None or not self.evidence):
            raise ValueError("present staff commitments require text and evidence")
        return self


class UnresolvedQuestion(StrictModel):
    question: NonEmptyText
    state: Literal[ValueState.UNKNOWN, ValueState.MISSING, ValueState.UNVERIFIED]
    evidence: tuple[EvidenceReference, ...] = ()


class IdentityClaim(StrictModel):
    state: Literal[ValueState.UNKNOWN, ValueState.UNVERIFIED, ValueState.PRESENT]
    label: NonEmptyText | None = None
    metadata_verified: bool = False

    @model_validator(mode="after")
    def verified_identity_requires_metadata(self) -> IdentityClaim:
        if self.state is ValueState.PRESENT and (self.label is None or not self.metadata_verified):
            raise ValueError("verified caller identity requires supporting metadata")
        if self.state is not ValueState.PRESENT and self.metadata_verified:
            raise ValueError("unverified identities cannot claim metadata verification")
        return self


class ExtractedFacts(StrictModel):
    caller_request: TextFact
    reported_facts: tuple[TextFact, ...]
    people_or_organizations: tuple[TextFact, ...]
    dates: tuple[DateFact, ...]
    appointments: tuple[AppointmentFact, ...]
    monetary_figures: tuple[MonetaryFigure, ...]
    staff_commitments: tuple[StaffCommitment, ...]
    requested_follow_up: TextFact
    unresolved_questions: tuple[UnresolvedQuestion, ...]
    missing_context: tuple[NonEmptyText, ...]
    caller_identity: IdentityClaim
    confidence: Confidence


class Finding(StrictModel):
    finding_id: OpaqueId
    kind: OpaqueId
    statement: NonEmptyText
    material: bool
    evidence: tuple[EvidenceReference, ...] = ()


class StructuredAnalysis(StrictModel):
    analysis_id: OpaqueId
    call_id: OpaqueId
    category: AnalysisCategory
    priority: Priority
    summary: NonEmptyText
    proposed_next_steps: tuple[NonEmptyText, ...]
    responsible_role: ResponsibleRole
    suggested_response_timing: NonEmptyText | None = None
    attorney_attention_issues: tuple[Finding, ...]
    dissatisfaction_indicators: tuple[Finding, ...]
    omitted_information_findings: tuple[Finding, ...]
    internal_file_note_draft: NonEmptyText
    confidence: Confidence
    findings: tuple[Finding, ...]
    acceptance_state: AnalysisAcceptanceState
    advisory_status: AdvisoryStatus
    facts: ExtractedFacts
    provenance: Provenance


class SanitizedProcessingFailure(StrictModel):
    failure_class: FailureClass
    terminal_state: Literal[
        ProcessingState.AUDIO_INVALID,
        ProcessingState.TRANSCRIPTION_FAILED,
        ProcessingState.OUTPUT_VALIDATION_FAILED,
        ProcessingState.ANALYSIS_FAILED,
    ]
    diagnostic_code: OpaqueId
    retryable: bool


class ProcessingAttempt(StrictModel):
    attempt_id: OpaqueId
    call_id: OpaqueId
    attempt_number: Annotated[int, Field(ge=1)]
    state: ProcessingState
    started_at: AwareDatetime
    completed_at: AwareDatetime | None = None
    failure: SanitizedProcessingFailure | None = None
    provenance: Provenance


class PlaybookRule(StrictModel):
    rule_id: OpaqueId
    description: NonEmptyText
    evidence_required: bool
    outcome: NonEmptyText


class PlaybookVersion(StrictModel):
    playbook_id: OpaqueId
    version: OpaqueId
    label: NonEmptyText
    synthetic: Literal[True]
    status: PlaybookStatus
    allowed_responsible_roles: tuple[ResponsibleRole, ...]
    category_definitions: tuple[PlaybookRule, ...]
    priority_rules: tuple[PlaybookRule, ...]
    evidence_requirements: tuple[PlaybookRule, ...]
    routine_no_action_criteria: tuple[PlaybookRule, ...]
    dissatisfaction_indicators: tuple[PlaybookRule, ...]
    commitment_handling: tuple[PlaybookRule, ...]
    date_uncertainty_rules: tuple[PlaybookRule, ...]
    spanish_language_handling: tuple[PlaybookRule, ...]
    prompt_injection_boundary: tuple[PlaybookRule, ...]
    prohibited_conclusions: tuple[NonEmptyText, ...]
