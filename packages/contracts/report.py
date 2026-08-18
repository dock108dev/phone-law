"""Strict, versioned contracts for the synthetic review experience."""

from __future__ import annotations

from datetime import date
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

from packages.contracts.review import (
    AnalysisCategory,
    Confidence,
    Direction,
    EvidenceReference,
    ExtractedFacts,
    Finding,
    ProcessingState,
    Provenance,
    ResponsibleRole,
    TranscriptSegment,
)

REPORT_SCHEMA_VERSION = "daily-report-v1"
REVIEW_SCHEMA_VERSION = "review-event-v1"
AUDIT_SCHEMA_VERSION = "audit-event-v1"
OpaqueId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")]
NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class ReportStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


class ReportSectionKind(StrEnum):
    IMMEDIATE_ATTENTION = "immediate_attention"
    POTENTIAL_NEW_MATTERS = "potential_new_matters"
    TIME_SENSITIVE_DATES = "time_sensitive_dates"
    DISSATISFACTION_ESCALATION = "dissatisfaction_escalation"
    STAFF_COMMITMENTS = "staff_commitments"
    ADMINISTRATIVE_TASKS = "administrative_tasks"
    ROUTINE_NO_ACTION = "routine_no_action"
    PROCESSING_FAILURES = "processing_failures"


class ReviewLabel(StrEnum):
    CORRECT = "correct"
    PARTIALLY_CORRECT = "partially_correct"
    INCORRECT = "incorrect"
    UNSUPPORTED = "unsupported"
    MISSING = "missing"
    NOT_APPLICABLE = "not_applicable"


class DemoRole(StrEnum):
    REVIEWER = "reviewer"
    ADMINISTRATOR = "administrator"
    OPERATIONS = "operations"


class DemoPrincipalId(StrEnum):
    REVIEWER = "demo-reviewer"
    ADMIN = "demo-admin"
    OPERATIONS = "demo-operations"


class PlaybookLifecycleState(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    RETIRED = "retired"


class DemoPrincipal(StrictModel):
    principal_id: DemoPrincipalId
    role: DemoRole
    synthetic: Literal[True] = True


class ReportReconciliation(StrictModel):
    expected: Annotated[int, Field(ge=0)]
    received: Annotated[int, Field(ge=0)]
    duplicate_deliveries: Annotated[int, Field(ge=0)]
    analyzed: Annotated[int, Field(ge=0)]
    failed: Annotated[int, Field(ge=0)]
    missing: Annotated[int, Field(ge=0)]
    late: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def counts_reconcile(self) -> ReportReconciliation:
        if self.received > self.expected:
            raise ValueError("received unique calls cannot exceed expected eligible calls")
        if self.analyzed + self.failed > self.received:
            raise ValueError("analyzed and failed calls cannot exceed received calls")
        if self.missing != self.expected - self.received:
            raise ValueError("missing count must reconcile expected and received calls")
        return self


class ReportCompleteness(StrictModel):
    status: ReportStatus
    explanation: NonEmptyText
    reconciliation: ReportReconciliation


class FailedCallSummary(StrictModel):
    call_id: OpaqueId
    synthetic_reference: OpaqueId
    failed_stage: NonEmptyText
    diagnostic_code: OpaqueId
    retryable: bool
    terminal_state: ProcessingState


class LateCallMarker(StrictModel):
    call_id: OpaqueId
    synthetic_reference: OpaqueId
    received_at: AwareDatetime
    cutoff_at: AwareDatetime


class ReportItem(StrictModel):
    item_id: OpaqueId
    call_id: OpaqueId
    synthetic_reference: OpaqueId
    analysis_id: OpaqueId | None = None
    section: ReportSectionKind
    summary: NonEmptyText
    category: AnalysisCategory | None = None
    priority: str
    confidence: Confidence | None = None
    responsible_role: ResponsibleRole | None = None
    suggested_timing: NonEmptyText | None = None
    evidence: tuple[EvidenceReference, ...] = ()
    provenance: Provenance | None = None
    failure: FailedCallSummary | None = None


class ReportSection(StrictModel):
    kind: ReportSectionKind
    title: NonEmptyText
    description: NonEmptyText
    items: tuple[ReportItem, ...]


class DailyReport(StrictModel):
    schema_version: Literal["daily-report-v1"]
    report_id: OpaqueId
    business_date: date
    timezone: Literal["America/New_York"]
    cutoff_at: AwareDatetime
    version: Annotated[int, Field(ge=1)]
    generated_at: AwareDatetime
    synthetic: Literal[True]
    advisory_notice: NonEmptyText
    completeness: ReportCompleteness
    sections: tuple[ReportSection, ...]
    late_calls: tuple[LateCallMarker, ...] = ()

    @model_validator(mode="after")
    def required_section_order(self) -> DailyReport:
        expected = tuple(ReportSectionKind)
        actual = tuple(section.kind for section in self.sections)
        if actual != expected:
            raise ValueError("daily report sections must use the required deterministic order")
        return self


class ReviewEvent(StrictModel):
    schema_version: Literal["review-event-v1"]
    event_id: OpaqueId
    analysis_id: OpaqueId
    finding_id: OpaqueId | None = None
    label: ReviewLabel
    note: NonEmptyText | None = None
    principal: DemoPrincipal
    created_at: AwareDatetime

    @model_validator(mode="after")
    def target_matches_label(self) -> ReviewEvent:
        if self.label is ReviewLabel.MISSING:
            if self.finding_id is not None or self.note is None:
                raise ValueError("missing feedback targets the analysis and requires a note")
        elif self.finding_id is None:
            raise ValueError("finding feedback requires an original finding identifier")
        return self


class AuditEvent(StrictModel):
    schema_version: Literal["audit-event-v1"]
    event_id: OpaqueId
    principal: DemoPrincipal
    action: OpaqueId
    target_type: OpaqueId
    target_id: OpaqueId
    result: OpaqueId
    created_at: AwareDatetime


class ReviewEventCreate(StrictModel):
    label: ReviewLabel
    finding_id: OpaqueId | None = None
    note: NonEmptyText | None = None

    @field_validator("label", mode="before")
    @classmethod
    def validate_json_label(cls, value: object) -> ReviewLabel:
        if isinstance(value, ReviewLabel):
            return value
        if isinstance(value, str):
            return ReviewLabel(value)
        raise ValueError("review label must be a supported string")


class ProcessingAttemptSummary(StrictModel):
    attempt_id: OpaqueId
    attempt_number: Annotated[int, Field(ge=1)]
    state: ProcessingState
    diagnostic_code: OpaqueId | None = None
    retryable: bool | None = None
    started_at: AwareDatetime
    completed_at: AwareDatetime | None = None


class CallDetail(StrictModel):
    call_id: OpaqueId
    synthetic_reference: OpaqueId
    synthetic: Literal[True]
    occurred_at: AwareDatetime
    direction: Direction
    duration_seconds: Annotated[float, Field(ge=0)]
    staff_extension: OpaqueId | None = None
    language: Literal["en", "es"]
    identity_state: str
    identity_label: NonEmptyText | None = None
    transcript_id: OpaqueId
    transcript_segments: tuple[TranscriptSegment, ...]
    analysis_id: OpaqueId
    summary: NonEmptyText
    category: AnalysisCategory
    priority: str
    confidence: Confidence
    uncertainty: tuple[NonEmptyText, ...]
    facts: ExtractedFacts
    findings: tuple[Finding, ...]
    proposed_next_steps: tuple[NonEmptyText, ...]
    responsible_role: ResponsibleRole
    suggested_response_timing: NonEmptyText | None = None
    provenance: Provenance
    attempts: tuple[ProcessingAttemptSummary, ...]
    review_history: tuple[ReviewEvent, ...]


class FailureQueueItem(StrictModel):
    call_id: OpaqueId
    synthetic_reference: OpaqueId
    failed_stage: NonEmptyText
    diagnostic_code: OpaqueId
    retryable: bool
    first_attempt_at: AwareDatetime
    latest_attempt_at: AwareDatetime
    attempt_count: Annotated[int, Field(ge=1)]
    current_terminal_state: ProcessingState
    resolved: bool
    attempt_history: tuple[ProcessingAttemptSummary, ...]


class FailureQueue(StrictModel):
    current: tuple[FailureQueueItem, ...]
    resolved: tuple[FailureQueueItem, ...]


class RetryResult(StrictModel):
    call_id: OpaqueId
    result: Literal["retry_completed"]
    terminal_state: ProcessingState
    attempt_count: Annotated[int, Field(ge=1)]


class PlaybookSummary(StrictModel):
    playbook_id: OpaqueId
    version: OpaqueId
    label: NonEmptyText
    synthetic: Literal[True]
    lifecycle: PlaybookLifecycleState
    categories: tuple[NonEmptyText, ...]
    key_rules: tuple[NonEmptyText, ...]
    created_at: AwareDatetime
    published_at: AwareDatetime | None = None


class PlaybookActionResult(StrictModel):
    playbook: PlaybookSummary
    result: Literal["published"]


class ReportDateList(StrictModel):
    dates: tuple[date, ...]


class ApiError(StrictModel):
    error: NonEmptyText
    correlation_id: OpaqueId
