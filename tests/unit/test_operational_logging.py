from __future__ import annotations

import json

from packages.observability.logging import OperationalLogger, normalize_correlation_id


def test_operational_logger_drops_content_and_secret_fields(caplog: object) -> None:
    logger = OperationalLogger("api")
    logger.event(
        "safe_event",
        status="ready",
        correlation_id="slice0-test-002",
        transcript="content must disappear",
        authorization="Bearer value-must-disappear",
        provider_url="https://provider.invalid/private",
        phone_number="5550000000",
    )
    line = str(caplog.messages[-1])
    payload = json.loads(line)

    assert payload["event"] == "safe_event"
    assert payload["status"] == "ready"
    assert "transcript" not in line
    assert "authorization" not in line
    assert "provider" not in line
    assert "5550000000" not in line


def test_correlation_id_accepts_safe_value_and_replaces_unsafe_value() -> None:
    assert normalize_correlation_id("request-1234") == "request-1234"
    generated = normalize_correlation_id("contains client content")
    assert len(generated) == 32
    assert generated.isalnum()
