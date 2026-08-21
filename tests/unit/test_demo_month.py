from collections import Counter
from datetime import date

from packages.contracts.review import Provenance
from packages.review.demo_month import DemoMonthCallSource, DemoMonthManifest
from packages.review.fixtures import FixtureAnalyzer, FixtureTranscriber


def test_demo_month_manifest_reconciles_exact_contract() -> None:
    manifest = DemoMonthManifest()

    assert manifest.version == "demo-month-2026-07-v1"
    assert manifest.seed == 60819
    assert len(manifest.entries()) == 500
    assert len(manifest.received_entries()) == 498
    assert Counter(item["outcome"] for item in manifest.entries()) == {
        "analyzed": 490,
        "failed": 8,
        "missing": 2,
    }
    assert (
        Counter(item["category"] for item in manifest.entries()) == manifest.contract["categories"]
    )
    assert (
        Counter(item["language"] for item in manifest.entries()) == manifest.contract["languages"]
    )
    assert len(manifest.expected_entries(date(2026, 7, 4))) == 0
    assert len(manifest.expected_entries(date(2026, 7, 28))) == 23
    assert manifest.summary()["business_month"] == "2026-07"


def test_demo_month_events_are_stable_transcript_only_artifacts() -> None:
    manifest = DemoMonthManifest()
    source = DemoMonthCallSource(manifest)
    events = source.events()

    assert len(events) == 498
    assert events[0].call.source.value == "transcript_only"
    assert events[0].call.media_reference is None
    assert events[0].call.synthetic is True
    assert source.events("CL-MONTH-202607-001") == (events[0],)

    scenario_inventory = Counter(
        scenario for entry in manifest.entries() for scenario in entry["scenarios"]
    )
    assert all(scenario_inventory[item] > 0 for item in manifest.contract["scenario_contract"])


def test_spanish_and_unverified_date_content_survive_fixture_adapters() -> None:
    manifest = DemoMonthManifest()
    source = DemoMonthCallSource(manifest)
    transcriber = FixtureTranscriber(manifest)  # type: ignore[arg-type]
    analyzer = FixtureAnalyzer(manifest)  # type: ignore[arg-type]

    spanish_entry = next(item for item in manifest.entries() if item["language"] == "es")
    spanish_event = source.events(str(spanish_entry["fixture_id"]))[0]
    provenance = Provenance(
        schema_version="review-contracts-v1",
        call_source=spanish_event.call.source,
        source_event_id=spanish_event.call.source_event_id,
        source_call_id=spanish_event.call.source_call_id,
        transcript_adapter="fixture-transcriber",
        transcript_model_version="deterministic-transcript-v1",
        analysis_adapter="fixture-analyzer",
        analysis_model_version="deterministic-analysis-v1",
        prompt_version="facts-first-prompt-v1",
        playbook_version="synthetic-draft-v1",
        adapter_version="fixture-analyzer-v1",
        generated_at=spanish_event.received_at,
        processing_attempt_id="demo-month-unit-attempt",
        environment="fixture",
    )
    transcript = transcriber.transcribe(
        spanish_event.call,
        fixture_id=str(spanish_entry["fixture_id"]),
        call_id="demo-month-unit-call",
        attempt_number=1,
        provenance=provenance,
    )
    assert transcript.language == "es"
    assert transcript.original_language_text == " ".join(item.text for item in transcript.segments)

    date_entry = next(
        item
        for item in manifest.entries()
        if "relative_unverified_date_reference" in item["scenarios"]
    )
    date_event = source.events(str(date_entry["fixture_id"]))[0]
    date_transcript = transcriber.transcribe(
        date_event.call,
        fixture_id=str(date_entry["fixture_id"]),
        call_id="demo-month-date-call",
        attempt_number=1,
        provenance=provenance,
    )
    facts = analyzer.extract_facts(str(date_entry["fixture_id"]), date_transcript)
    assert facts.dates[0].state.value == "unverified"
    assert facts.dates[0].iso_date is None
    assert facts.dates[0].is_deadline is False
