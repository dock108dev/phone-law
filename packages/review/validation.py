"""Application-level evidence and accepted-analysis validation."""

from __future__ import annotations

from collections.abc import Iterable

from packages.contracts.review import (
    AnalysisAcceptanceState,
    EvidenceReference,
    ExtractedFacts,
    Finding,
    Priority,
    StructuredAnalysis,
    TimestampAvailability,
    Transcript,
    TranscriptValidationState,
    ValueState,
)


class ReviewValidationError(ValueError):
    """Named validation failure safe to record without source content."""


def _evidence_from_facts(facts: ExtractedFacts) -> Iterable[EvidenceReference]:
    yield from facts.caller_request.evidence
    yield from facts.requested_follow_up.evidence
    for fact in facts.reported_facts:
        yield from fact.evidence
    for entity in facts.people_or_organizations:
        yield from entity.evidence
    for date in facts.dates:
        yield from date.evidence
    for appointment in facts.appointments:
        yield from appointment.evidence
        if appointment.date:
            yield from appointment.date.evidence
    for amount in facts.monetary_figures:
        yield from amount.evidence
    for commitment in facts.staff_commitments:
        yield from commitment.evidence
        if commitment.timing:
            yield from commitment.timing.evidence
    for question in facts.unresolved_questions:
        yield from question.evidence


def _findings(analysis: StructuredAnalysis) -> Iterable[Finding]:
    yield from analysis.findings
    yield from analysis.attorney_attention_issues
    yield from analysis.dissatisfaction_indicators
    yield from analysis.omitted_information_findings


def validate_evidence(
    reference: EvidenceReference, transcript: Transcript, duration: float
) -> None:
    segments = {segment.segment_id: segment for segment in transcript.segments}
    segment = segments.get(reference.segment_id)
    if segment is None:
        raise ReviewValidationError("evidence_segment_not_found")
    if reference.start_seconds < 0 or reference.end_seconds > duration:
        raise ReviewValidationError("evidence_outside_call_duration")
    if reference.start_seconds >= reference.end_seconds:
        raise ReviewValidationError("evidence_timestamp_order_invalid")
    if segment.start_seconds is None or segment.end_seconds is None:
        raise ReviewValidationError("evidence_timestamps_unavailable")
    if (
        reference.start_seconds < segment.start_seconds
        or reference.end_seconds > segment.end_seconds
    ):
        raise ReviewValidationError("evidence_outside_segment")
    if reference.speaker is not segment.speaker:
        raise ReviewValidationError("evidence_speaker_mismatch")
    if reference.excerpt not in segment.text:
        raise ReviewValidationError("evidence_excerpt_unsupported")


def validate_analysis(
    analysis: StructuredAnalysis,
    transcript: Transcript,
    duration_seconds: float,
    *,
    caller_identity_metadata_verified: bool = False,
) -> None:
    if transcript.timestamp_availability is TimestampAvailability.UNAVAILABLE:
        raise ReviewValidationError("transcript_timestamps_unavailable")
    if transcript.validation_state is not TranscriptValidationState.ACCEPTED:
        raise ReviewValidationError("transcript_requires_human_review")
    for reference in _evidence_from_facts(analysis.facts):
        validate_evidence(reference, transcript, duration_seconds)
    findings = tuple(_findings(analysis))
    for finding in findings:
        if finding.material and not finding.evidence:
            raise ReviewValidationError("material_finding_missing_evidence")
        for reference in finding.evidence:
            validate_evidence(reference, transcript, duration_seconds)
    if analysis.priority in {Priority.HIGH, Priority.IMMEDIATE} and not any(
        finding.evidence for finding in findings if finding.material
    ):
        raise ReviewValidationError("high_priority_output_missing_evidence")
    if (
        analysis.facts.caller_identity.state is ValueState.PRESENT
        and not caller_identity_metadata_verified
    ):
        raise ReviewValidationError("verified_caller_identity_missing_metadata")
    if analysis.acceptance_state is not AnalysisAcceptanceState.ACCEPTED:
        raise ReviewValidationError("analysis_not_accepted")


def acceptance_state_for(
    analysis: StructuredAnalysis,
    transcript: Transcript,
    duration_seconds: float,
    *,
    caller_identity_metadata_verified: bool = False,
) -> AnalysisAcceptanceState:
    """Classify invalid candidates without ever treating them as accepted output."""

    try:
        validate_analysis(
            analysis,
            transcript,
            duration_seconds,
            caller_identity_metadata_verified=caller_identity_metadata_verified,
        )
    except ReviewValidationError as exc:
        if analysis.priority in {Priority.HIGH, Priority.IMMEDIATE} and str(exc) in {
            "material_finding_missing_evidence",
            "high_priority_output_missing_evidence",
        }:
            return AnalysisAcceptanceState.NEEDS_REVIEW
        return AnalysisAcceptanceState.REJECTED
    return AnalysisAcceptanceState.ACCEPTED


def transcript_validation_state(transcript: Transcript) -> TranscriptValidationState:
    """Name the safe downstream state before any facts or findings are produced."""

    if transcript.validation_state is not TranscriptValidationState.ACCEPTED:
        return transcript.validation_state
    if transcript.timestamp_availability is TimestampAvailability.UNAVAILABLE:
        return TranscriptValidationState.REQUIRES_HUMAN_REVIEW
    if not transcript.segments:
        return TranscriptValidationState.REJECTED
    return TranscriptValidationState.ACCEPTED
