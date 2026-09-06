"""Review authored v2 conversations against independent expectations and persisted recaps."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from packages.contracts.report import BriefingCall
from packages.review.demo_month import DemoMonthManifest

ROOT = Path(__file__).parents[2] / "fixtures/demo-month"


def expectations() -> dict[str, Any]:
    month = json.loads((ROOT / "month-expectations-v2.json").read_text())["calls"]
    morning = json.loads((ROOT / "morning-expectations-v1.json").read_text())["calls"]
    return {
        **{item["fixture_id"]: item for item in month},
        **{f"CL-AM-20260715-{item['number']:02}": item for item in morning},
    }


def review_recap(recap: BriefingCall, oracle: dict[str, Any]) -> int:
    """Check an actual projection, including original-language passages and uncertainty."""
    detail = recap.detail
    if oracle.get("expected_result") == "unavailable":
        assert detail is None and recap.state == "unavailable" and not recap.attention
        return 0
    assert detail is not None, recap.synthetic_reference
    assert detail.identity_label == oracle["caller"], recap.synthetic_reference
    assert [item.kind for item in recap.attention] == oracle["attention"], recap.synthetic_reference
    for term in oracle["summary_terms"]:
        assert term.lower() in detail.summary.lower(), (recap.synthetic_reference, term)
    assert bool(detail.uncertainty) == bool(oracle["unknown"]), recap.synthetic_reference
    assert bool(detail.facts.requested_follow_up.value) == bool(oracle["request"])
    assert bool(detail.facts.staff_commitments) == bool(oracle["promise"])
    assert bool(detail.proposed_next_steps) == bool(oracle["suggestion"])
    originals = {s.segment_id: s.text for s in detail.transcript_segments}
    for segment_id, text in oracle["support"].items():
        assert originals[segment_id] == text, (recap.synthetic_reference, segment_id)
    count = 0

    def inspect(value: Any) -> None:
        nonlocal count
        if isinstance(value, dict):
            if "excerpt" in value and "segment_id" in value:
                assert originals[value["segment_id"]] == value["excerpt"]
                count += 1
            for child in value.values():
                inspect(child)
        elif isinstance(value, list):
            for child in value:
                inspect(child)

    inspect(detail.facts.model_dump(mode="json"))
    inspect([item.model_dump(mode="json") for item in recap.attention])
    return count


def verify_originals(manifest: DemoMonthManifest) -> None:
    originals = json.loads((ROOT / "month-transcripts-v2.json").read_text())["calls"]
    seen: set[str] = set()
    for item in originals:
        assert manifest.entry(item["fixture_id"])["transcript"]["segments"] == item["segments"]
        dialogue = json.dumps([s["text"] for s in item["segments"]], ensure_ascii=False)
        assert dialogue not in seen, "repeated dialogue"
        seen.add(dialogue)
    morning = DemoMonthManifest(ROOT / "morning-v1.json")
    for entry in morning.entries():
        included = manifest.entry(entry["fixture_id"])
        for key in ("transcript", "expected_facts", "expected_analysis", "scenarios"):
            assert included[key] == entry[key], (entry["fixture_id"], key)
        for key in (
            "source_call_id",
            "source_event_id",
            "occurred_at",
            "transcript_fixture_reference",
        ):
            assert included["event"]["call"][key] == entry["event"]["call"][key]
    assert len(originals) == 215
    assert len(expectations()) == 225
