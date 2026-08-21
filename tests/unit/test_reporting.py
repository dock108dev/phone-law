from __future__ import annotations

from datetime import date, datetime
from typing import Any, cast
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from packages.contracts.report import (
    DemoPrincipal,
    DemoPrincipalId,
    DemoRole,
    FailedCallSummary,
    ReportSectionKind,
    ReportStatus,
    ReviewEvent,
    ReviewLabel,
)
from packages.contracts.review import ProcessingState, Provenance, StructuredAnalysis
from packages.review.fixtures import FixtureAnalyzer, FixtureCallSource, FixtureTranscriber
from packages.review.reporting import ReportCallInput, aggregate_daily_report


def analysis_for(fixture_id: str, call_id: str) -> StructuredAnalysis:
    source = FixtureCallSource()
    event = source.events(fixture_id)[0]
    provenance = Provenance(
        schema_version=cast(Any, "review-contracts-v1"),
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
        processing_attempt_id=f"attempt-{fixture_id.lower()}",
        environment="fixture",
    )
    transcript = FixtureTranscriber(source.manifest).transcribe(
        event.call,
        fixture_id=fixture_id,
        call_id=call_id,
        attempt_number=1,
        provenance=provenance,
    )
    analyzer = FixtureAnalyzer(source.manifest)
    facts = analyzer.extract_facts(fixture_id, transcript)
    return analyzer.apply_playbook(
        fixture_id,
        call_id=call_id,
        facts=facts,
        transcript=transcript,
        provenance=provenance,
    )


def test_deterministic_partial_report_reconciles_and_orders_sections() -> None:
    timezone = ZoneInfo("America/New_York")
    cutoff = datetime(2026, 8, 17, 18, tzinfo=timezone)
    source = FixtureCallSource()
    event_002 = source.events("CL-FX-002")[0]
    event_004 = source.events("CL-FX-004")[0]
    event_011 = source.events("CL-FX-011")[0]
    call_002 = "callid002000000000000000000000000"
    call_004 = "callid004000000000000000000000000"
    call_011 = "callid011000000000000000000000000"
    failure = FailedCallSummary(
        call_id=call_011,
        synthetic_reference="CL-FX-011",
        failed_stage="media validation",
        diagnostic_code="fixture_media_permanent",
        retryable=False,
        terminal_state=ProcessingState.AUDIO_INVALID,
    )
    report = aggregate_daily_report(
        business_date=date(2026, 8, 17),
        cutoff_at=cutoff,
        expected_source_call_ids=(
            event_002.call.source_call_id,
            event_004.call.source_call_id,
            event_011.call.source_call_id,
        ),
        calls=(
            ReportCallInput(
                call_id=call_004,
                synthetic_reference="CL-FX-004",
                source_call_id=event_004.call.source_call_id,
                occurred_at=event_004.call.occurred_at,
                received_at=event_004.received_at,
                state=ProcessingState.ANALYZED,
                analysis=analysis_for("CL-FX-004", call_004),
                failure=None,
            ),
            ReportCallInput(
                call_id=call_002,
                synthetic_reference="CL-FX-002",
                source_call_id=event_002.call.source_call_id,
                occurred_at=event_002.call.occurred_at,
                received_at=event_002.received_at,
                state=ProcessingState.ANALYZED,
                analysis=analysis_for("CL-FX-002", call_002),
                failure=None,
            ),
            ReportCallInput(
                call_id=call_011,
                synthetic_reference="CL-FX-011",
                source_call_id=event_011.call.source_call_id,
                occurred_at=event_011.call.occurred_at,
                received_at=event_011.received_at,
                state=ProcessingState.AUDIO_INVALID,
                analysis=None,
                failure=failure,
            ),
        ),
        duplicate_deliveries=2,
        version=1,
        fingerprint="a" * 64,
    )
    assert report.completeness.status is ReportStatus.PARTIAL
    assert report.completeness.reconciliation.model_dump() == {
        "expected": 3,
        "received": 3,
        "duplicate_deliveries": 2,
        "analyzed": 2,
        "failed": 1,
        "missing": 0,
        "late": 0,
    }
    assert tuple(section.kind for section in report.sections) == tuple(ReportSectionKind)
    immediate = report.sections[0]
    assert [item.synthetic_reference for item in immediate.items] == ["CL-FX-004"]
    commitments = next(
        section
        for section in report.sections
        if section.kind is ReportSectionKind.STAFF_COMMITMENTS
    )
    assert commitments.items[0].synthetic_reference == "CL-FX-002"
    assert commitments.items[0].evidence[0].segment_id == "fx002-seg-4"
    failures = report.sections[-1]
    assert failures.items[0].failure == failure


def test_failed_report_and_strict_missing_review_contract() -> None:
    timezone = ZoneInfo("America/New_York")
    report = aggregate_daily_report(
        business_date=date(2026, 8, 17),
        cutoff_at=datetime(2026, 8, 17, 18, tzinfo=timezone),
        expected_source_call_ids=("expected-call",),
        calls=(),
        duplicate_deliveries=0,
        version=1,
        fingerprint="b" * 64,
    )
    assert report.completeness.status is ReportStatus.FAILED
    principal = DemoPrincipal(
        principal_id=DemoPrincipalId.REVIEWER,
        role=DemoRole.REVIEWER,
        synthetic=True,
    )
    with pytest.raises(ValidationError, match="requires a note"):
        ReviewEvent(
            schema_version="review-event-v1",
            event_id="review-event-001",
            analysis_id="analysis-001",
            finding_id=None,
            label=ReviewLabel.MISSING,
            note=None,
            principal=principal,
            created_at=datetime(2026, 8, 17, 17, tzinfo=timezone),
        )
