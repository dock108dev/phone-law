"""Independent schedule, morning-preservation and fail-closed content contracts."""

import json
from collections import Counter
from datetime import date
from pathlib import Path

import pytest

from packages.review.demo_month import DemoMonthManifest
from packages.review.month_content_review import verify_originals


def test_authored_month_has_independent_schedule_and_scenarios() -> None:
    manifest = DemoMonthManifest()
    assert manifest.version == "demo-month-2026-07-v2"
    assert manifest.seed == 20260702
    # Authored July calendar, including weekends and the July 3 closure.
    expected = [
        8,
        10,
        0,
        0,
        0,
        9,
        12,
        10,
        8,
        14,
        0,
        0,
        10,
        12,
        10,
        9,
        13,
        0,
        0,
        6,
        14,
        10,
        11,
        8,
        0,
        0,
        12,
        10,
        9,
        12,
        10,
    ]
    assert [len(manifest.expected_entries(date(2026, 7, d))) for d in range(1, 32)] == expected
    assert Counter(e["outcome"] for e in manifest.entries()) == {
        "analyzed": 224,
        "failed": 2,
        "missing": 1,
    }
    assert Counter(e["language"] for e in manifest.entries()) == {"en": 195, "es": 32}
    assert manifest.entry("CL-M2-20260707-02").get("transcript") is None
    assert manifest.entry("CL-M2-20260723-04").get("transcript") is None
    assert manifest.entry("CL-M2-20260727-03").get("expected_analysis") is None
    assert manifest.entry("CL-M2-20260727-03")["transcript"]
    assert sum("late_delivery" in e["scenarios"] for e in manifest.entries()) == 3
    assert sum("duplicate_delivery" in e["scenarios"] for e in manifest.entries()) == 3
    verify_originals(manifest)


def test_referenced_content_tampering_is_rejected(tmp_path: Path) -> None:
    source = Path("fixtures/demo-month/manifest-v2.json")
    contract = json.loads(source.read_text())
    contract["content_sha256"] = {"altered.json": "0" * 64}
    (tmp_path / "altered.json").write_text("{}")
    (tmp_path / "manifest.json").write_text(json.dumps(contract))
    with pytest.raises(ValueError, match="digest mismatch"):
        DemoMonthManifest(tmp_path / "manifest.json")
