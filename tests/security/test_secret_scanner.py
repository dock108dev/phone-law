from __future__ import annotations

from pathlib import Path

from scripts.secret_scan import scan_paths


def test_secret_scanner_detects_high_signal_credential(tmp_path: Path) -> None:
    unsafe = tmp_path / "unsafe.txt"
    synthetic_token = "token=sk-" + "proj-" + "abcdefghijklmnopqrstuvwxyz123456"
    unsafe.write_text(synthetic_token, encoding="utf-8")
    findings = scan_paths([unsafe])
    assert [(finding.line, finding.kind) for finding in findings] == [(1, "openai_key")]


def test_secret_scanner_allows_documented_demo_placeholder(tmp_path: Path) -> None:
    safe = tmp_path / ".env.example"
    safe.write_text("APP_SECRET=demo-placeholder-not-a-deployable-secret", encoding="utf-8")
    assert scan_paths([safe]) == []
