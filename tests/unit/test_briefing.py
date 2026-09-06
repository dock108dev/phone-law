import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from packages.contracts.report import CallDetail
from packages.contracts.review import Provenance
from packages.review.demo_month import DemoMonthCallSource, DemoMonthManifest
from packages.review.fixtures import FixtureAnalyzer, FixtureTranscriber
from packages.review.reporting import briefing_call, prior_calendar_day

ROOT = Path("fixtures/demo-month")


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        ("2026-07-20T13:00:00+00:00", "2026-07-19"),
        ("2026-07-16T02:00:00+00:00", "2026-07-14"),
        ("2026-03-09T05:00:00+00:00", "2026-03-08"),
        ("2026-11-02T05:00:00+00:00", "2026-11-01"),
    ],
)
def test_prior_day_never_skips_calendar_dates(now: str, expected: str) -> None:
    assert prior_calendar_day(datetime.fromisoformat(now)) == date.fromisoformat(expected)


def test_unavailable_call_has_no_fabricated_content() -> None:
    result = briefing_call(
        call_id="call-unavailable",
        synthetic_reference="FX-failed",
        occurred_at=datetime.now(UTC),
        detail=None,
    )
    assert result.state == "unavailable"
    assert result.detail is None and result.attention == ()


@pytest.mark.parametrize("number", range(1, 11))
def test_independent_transcript_expectation(number: int) -> None:
    manifest = DemoMonthManifest(ROOT / "morning-v1.json")
    oracle = json.loads((ROOT / "morning-expectations-v1.json").read_text())["calls"][number - 1]
    authored = json.loads((ROOT / "morning-transcripts-v1.json").read_text())["calls"][number - 1]
    source = DemoMonthCallSource(manifest)
    event = source.events()[number - 1]
    entry = manifest.entry(event.fixture_id)
    assert entry["transcript"]["segments"] == authored["segments"]
    by_id = {s["segment_id"]: s["text"] for s in authored["segments"]}
    for segment_id, quotation in oracle["support"].items():
        assert by_id[segment_id] == quotation
    provenance = Provenance.model_validate_json(
        json.dumps(
            {
                "schema_version": "review-contracts-v1",
                "call_source": event.call.source.value,
                "source_event_id": event.call.source_event_id,
                "source_call_id": event.call.source_call_id,
                "transcript_adapter": "fixture-transcriber",
                "transcript_model_version": "deterministic-transcript-v1",
                "analysis_adapter": "fixture-analyzer",
                "analysis_model_version": "deterministic-analysis-v1",
                "prompt_version": "facts-first-prompt-v1",
                "playbook_version": "synthetic-draft-v1",
                "adapter_version": "fixture-analyzer-v1",
                "generated_at": event.received_at.isoformat(),
                "processing_attempt_id": "attempt-morning",
                "environment": "fixture",
            }
        )
    )
    transcript = FixtureTranscriber(cast(Any, manifest)).transcribe(
        event.call,
        fixture_id=event.fixture_id,
        call_id="call-morning",
        attempt_number=1,
        provenance=provenance,
    )
    analyzer = FixtureAnalyzer(cast(Any, manifest))
    facts = analyzer.extract_facts(event.fixture_id, transcript)
    analysis = analyzer.apply_playbook(
        event.fixture_id,
        call_id="call-morning",
        facts=facts,
        transcript=transcript,
        provenance=provenance,
    )
    detail = CallDetail(
        call_id="call-morning",
        synthetic_reference=event.fixture_id,
        synthetic=True,
        occurred_at=event.call.occurred_at,
        direction=event.call.direction,
        duration_seconds=event.call.duration_seconds,
        language=transcript.language,
        identity_state=facts.caller_identity.state.value,
        identity_label=facts.caller_identity.label,
        transcript_id=transcript.transcript_id,
        transcript_segments=transcript.segments,
        analysis_id=analysis.analysis_id,
        summary=analysis.summary,
        category=analysis.category,
        priority=analysis.priority.value,
        confidence=analysis.confidence,
        uncertainty=facts.missing_context,
        facts=facts,
        findings=analysis.attorney_attention_issues,
        proposed_next_steps=analysis.proposed_next_steps,
        responsible_role=analysis.responsible_role,
        provenance=provenance,
        attempts=(),
        review_history=(),
    )
    recap = briefing_call(
        call_id=detail.call_id,
        synthetic_reference=event.fixture_id,
        occurred_at=event.call.occurred_at,
        detail=detail,
    )
    assert detail.identity_label == oracle["caller"]
    assert [item.kind for item in recap.attention] == oracle["attention"]
    for term in oracle["summary_terms"]:
        assert term.lower() in detail.summary.lower()
    assert bool(detail.uncertainty) == bool(oracle["unknown"])
    assert bool(facts.requested_follow_up.value) == bool(oracle["request"])
    assert bool(facts.staff_commitments) == bool(oracle["promise"])
    assert bool(detail.proposed_next_steps) == bool(oracle["suggestion"])
    for item in recap.attention:
        for evidence in item.evidence:
            assert evidence.excerpt == by_id[evidence.segment_id]
            assert evidence.segment_id.startswith(f"am{number:02}-")


def test_morning_is_ten_unique_calls_and_bounded_coverage() -> None:
    manifest = DemoMonthManifest(ROOT / "morning-v1.json")
    assert len({e["fixture_id"] for e in manifest.entries()}) == 10
    assert manifest.contract["coverage_dates"] == ["2026-07-15"]
    assert manifest.contract["scenario"]["simulated_morning"] == "2026-07-16"
