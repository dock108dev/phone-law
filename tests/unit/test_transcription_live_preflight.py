from __future__ import annotations

from scripts.transcription_live_preflight import _is_present


class PresenceOnlyEnvironment(dict[str, str]):
    def __contains__(self, key: object) -> bool:
        return key == "OPENAI_API_KEY"

    def __getitem__(self, key: str) -> str:
        raise AssertionError(f"sensitive value was accessed: {key}")


def test_sensitive_preflight_gate_observes_presence_without_accessing_value() -> None:
    environment = PresenceOnlyEnvironment()
    assert _is_present(environment, "OPENAI_API_KEY") is True
    assert _is_present(environment, "OPENAI_PROJECT_ID") is False
