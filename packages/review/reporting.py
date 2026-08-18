"""Deterministic application-code aggregation for synthetic daily reports."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime

from packages.contracts.report import (
    DailyReport,
    FailedCallSummary,
    LateCallMarker,
    ReportCompleteness,
    ReportItem,
    ReportReconciliation,
    ReportSection,
    ReportSectionKind,
    ReportStatus,
)
from packages.contracts.review import (
    AnalysisCategory,
    EvidenceReference,
    Priority,
    ProcessingState,
    StructuredAnalysis,
)

ADVISORY_NOTICE = (
    "Synthetic recommendations only. Every finding requires human review before any action."
)
SECTION_COPY: dict[ReportSectionKind, tuple[str, str]] = {
    ReportSectionKind.IMMEDIATE_ATTENTION: (
        "Immediate attention",
        "High-priority synthetic findings that should be reviewed first.",
    ),
    ReportSectionKind.POTENTIAL_NEW_MATTERS: (
        "Potential new matters",
        "Calls containing a supported request for a new consultation.",
    ),
    ReportSectionKind.TIME_SENSITIVE_DATES: (
        "Time-sensitive dates",
        "Confirmed and explicitly unverified date references for human review.",
    ),
    ReportSectionKind.DISSATISFACTION_ESCALATION: (
        "Dissatisfaction and escalation",
        "Supported dissatisfaction indicators that may need supervisory review.",
    ),
    ReportSectionKind.STAFF_COMMITMENTS: (
        "Staff commitments",
        "Commitments stated by staff, with exact transcript evidence.",
    ),
    ReportSectionKind.ADMINISTRATIVE_TASKS: (
        "Administrative tasks",
        "Supported follow-up and administrative requests for human handling.",
    ),
    ReportSectionKind.ROUTINE_NO_ACTION: (
        "Routine / no action",
        "Routine informational calls that do not suggest further action.",
    ),
    ReportSectionKind.PROCESSING_FAILURES: (
        "Processing failures",
        "Calls without a reviewable result, shown without call content.",
    ),
}
PRIORITY_ORDER = {"immediate": 0, "high": 1, "normal": 2, "low": 3, "failure": 4}


@dataclass(frozen=True)
class ReportCallInput:
    call_id: str
    synthetic_reference: str
    source_call_id: str
    occurred_at: datetime
    received_at: datetime
    state: ProcessingState
    analysis: StructuredAnalysis | None
    failure: FailedCallSummary | None


def _evidence(
    analysis: StructuredAnalysis, section: ReportSectionKind
) -> tuple[EvidenceReference, ...]:
    candidates: list[EvidenceReference] = []
    if section is ReportSectionKind.STAFF_COMMITMENTS:
        for commitment in analysis.facts.staff_commitments:
            candidates.extend(commitment.evidence)
    elif section is ReportSectionKind.TIME_SENSITIVE_DATES:
        for date_fact in analysis.facts.dates:
            candidates.extend(date_fact.evidence)
    elif section is ReportSectionKind.DISSATISFACTION_ESCALATION:
        for finding in analysis.dissatisfaction_indicators:
            candidates.extend(finding.evidence)
    elif section in {
        ReportSectionKind.POTENTIAL_NEW_MATTERS,
        ReportSectionKind.ADMINISTRATIVE_TASKS,
        ReportSectionKind.ROUTINE_NO_ACTION,
    }:
        candidates.extend(analysis.facts.caller_request.evidence)
        candidates.extend(analysis.facts.requested_follow_up.evidence)
    else:
        for finding in (
            *analysis.attorney_attention_issues,
            *analysis.dissatisfaction_indicators,
            *analysis.omitted_information_findings,
            *analysis.findings,
        ):
            candidates.extend(finding.evidence)
    unique: dict[str, EvidenceReference] = {}
    for reference in candidates:
        unique.setdefault(reference.segment_id, reference)
    return tuple(unique.values())


def _sections_for(analysis: StructuredAnalysis) -> tuple[ReportSectionKind, ...]:
    sections: list[ReportSectionKind] = []
    if analysis.priority in {Priority.IMMEDIATE, Priority.HIGH}:
        sections.append(ReportSectionKind.IMMEDIATE_ATTENTION)
    if analysis.category is AnalysisCategory.NEW_INTAKE:
        sections.append(ReportSectionKind.POTENTIAL_NEW_MATTERS)
    if analysis.facts.dates:
        sections.append(ReportSectionKind.TIME_SENSITIVE_DATES)
    if (
        analysis.category is AnalysisCategory.DISSATISFACTION_ESCALATION
        or analysis.dissatisfaction_indicators
    ):
        sections.append(ReportSectionKind.DISSATISFACTION_ESCALATION)
    if any(item.state.value == "present" for item in analysis.facts.staff_commitments):
        sections.append(ReportSectionKind.STAFF_COMMITMENTS)
    if analysis.category in {
        AnalysisCategory.ADMINISTRATIVE,
        AnalysisCategory.EXISTING_CLIENT_FOLLOW_UP,
        AnalysisCategory.UNKNOWN,
    }:
        sections.append(ReportSectionKind.ADMINISTRATIVE_TASKS)
    if analysis.category is AnalysisCategory.ROUTINE_NO_ACTION:
        sections.append(ReportSectionKind.ROUTINE_NO_ACTION)
    return tuple(sections)


def _identifier(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]


def _report_item(call: ReportCallInput, section: ReportSectionKind) -> ReportItem:
    analysis = call.analysis
    if analysis is None:
        if call.failure is None:
            raise ValueError("failure report items require a sanitized failure")
        return ReportItem(
            item_id=_identifier(call.source_call_id, section.value),
            call_id=call.call_id,
            synthetic_reference=call.synthetic_reference,
            analysis_id=None,
            section=section,
            summary="This synthetic call did not produce a reviewable result.",
            category=None,
            priority="failure",
            confidence=None,
            responsible_role=None,
            evidence=(),
            provenance=None,
            failure=call.failure,
        )
    return ReportItem(
        item_id=_identifier(call.source_call_id, section.value),
        call_id=call.call_id,
        synthetic_reference=call.synthetic_reference,
        analysis_id=analysis.analysis_id,
        section=section,
        summary=analysis.summary,
        category=analysis.category,
        priority=analysis.priority.value,
        confidence=analysis.confidence,
        responsible_role=analysis.responsible_role,
        suggested_timing=analysis.suggested_response_timing,
        evidence=_evidence(analysis, section),
        provenance=analysis.provenance,
        failure=None,
    )


def aggregate_daily_report(
    *,
    business_date: date,
    cutoff_at: datetime,
    expected_source_call_ids: tuple[str, ...],
    calls: tuple[ReportCallInput, ...],
    duplicate_deliveries: int,
    version: int,
    fingerprint: str,
) -> DailyReport:
    """Aggregate persisted call results without a model or report-generation prompt."""

    if cutoff_at.tzinfo is None:
        raise ValueError("report cutoff must be timezone-aware")
    expected = set(expected_source_call_ids)
    eligible = tuple(item for item in calls if item.source_call_id in expected)
    received_ids = {item.source_call_id for item in eligible}
    late = tuple(item for item in eligible if item.received_at > cutoff_at)
    analyzed = tuple(item for item in eligible if item.analysis is not None)
    failed = tuple(item for item in eligible if item.failure is not None and item.analysis is None)
    reconciliation = ReportReconciliation(
        expected=len(expected),
        received=len(received_ids),
        duplicate_deliveries=duplicate_deliveries,
        analyzed=len(analyzed),
        failed=len(failed),
        missing=len(expected - received_ids),
        late=len(late),
    )
    if len(analyzed) == reconciliation.expected and not (failed or late or reconciliation.missing):
        status = ReportStatus.COMPLETE
        explanation = "Every expected eligible synthetic call was received and analyzed by cutoff."
    elif analyzed:
        status = ReportStatus.PARTIAL
        explanation = (
            "At least one call is reviewable, but coverage is incomplete because a call is "
            "missing, late, or failed."
        )
    else:
        status = ReportStatus.FAILED
        explanation = "No reviewable synthetic call result could be produced."

    grouped: dict[ReportSectionKind, list[tuple[ReportCallInput, ReportItem]]] = {
        kind: [] for kind in ReportSectionKind
    }
    for call in analyzed:
        if call.analysis is None:
            continue
        for section in _sections_for(call.analysis):
            grouped[section].append((call, _report_item(call, section)))
    for call in failed:
        grouped[ReportSectionKind.PROCESSING_FAILURES].append(
            (call, _report_item(call, ReportSectionKind.PROCESSING_FAILURES))
        )

    sections: list[ReportSection] = []
    for kind in ReportSectionKind:
        title, description = SECTION_COPY[kind]
        ordered = sorted(
            grouped[kind],
            key=lambda pair: (
                PRIORITY_ORDER[pair[1].priority],
                pair[0].occurred_at,
                pair[0].synthetic_reference,
                pair[1].item_id,
            ),
        )
        sections.append(
            ReportSection(
                kind=kind,
                title=title,
                description=description,
                items=tuple(item for _, item in ordered),
            )
        )

    late_markers = tuple(
        LateCallMarker(
            call_id=item.call_id,
            synthetic_reference=item.synthetic_reference,
            received_at=item.received_at,
            cutoff_at=cutoff_at,
        )
        for item in sorted(late, key=lambda value: (value.received_at, value.synthetic_reference))
    )
    return DailyReport(
        schema_version="daily-report-v1",
        report_id=_identifier(str(business_date), fingerprint),
        business_date=business_date,
        timezone="America/New_York",
        cutoff_at=cutoff_at,
        version=version,
        generated_at=cutoff_at,
        synthetic=True,
        advisory_notice=ADVISORY_NOTICE,
        completeness=ReportCompleteness(
            status=status,
            explanation=explanation,
            reconciliation=reconciliation,
        ),
        sections=tuple(sections),
        late_calls=late_markers,
    )
