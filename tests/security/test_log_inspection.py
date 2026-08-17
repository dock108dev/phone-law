from __future__ import annotations

from scripts.inspect_logs import inspect


def test_log_inspection_accepts_content_free_operational_event() -> None:
    line = '{"event":"service_started","service":"api","status":"up"}'
    assert inspect(line) == []


def test_log_inspection_rejects_content_and_urls() -> None:
    findings = inspect('{"transcript":"content","endpoint":"https://provider.invalid"}')
    assert findings == ["transcript", "url"]
