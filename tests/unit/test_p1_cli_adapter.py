"""Adapter tests use injected doubles and never start a process."""

import json
from pathlib import Path

import pytest

from packages.config import Settings
from packages.review.transcript_import import load_transcript_only_artifact
from scripts.p1.cli_adapter import (
    AdapterError,
    MockRunner,
    OperatorSelection,
    Request,
    transcribe,
)


def context():
    artifact = load_transcript_only_artifact(
        Path("fixtures/transcript-only/invented-call.json").resolve()
    )
    return artifact.transcript.provenance


def output():
    return {
        "text": "Hola mundo",
        "segments": [
            {"speaker": "A", "start": 0, "end": 2, "text": "Hola"},
            {"speaker": "B", "start": 1, "end": 3, "text": "mundo"},
        ],
    }


def invoke(data):
    return transcribe(
        OperatorSelection(),
        Request(b"generated", 4, "es"),
        context(),
        "call-001",
        runner=MockRunner(json.dumps(data).encode()),
    )


def test_conversion_overlap_and_safe_mock_provenance():
    result = invoke(output())
    assert result.original_language_text == "Hola mundo"
    assert result.segments[0].identity.raw_provider_speaker_label == "speaker-001"
    assert result.segments[1].identity.raw_provider_speaker_label == "speaker-002"
    assert result.provenance.transcription_transport.result_kind == "mocked_cli"
    assert result.provenance.transcription_transport.observed_cli_version == "unavailable"
    assert all(s.speaker.value == "unknown_participant" for s in result.segments)


def test_repeated_speaker_is_stable():
    data = output()
    data["segments"][1]["speaker"] = "A"
    result = invoke(data)
    assert result.segments[0].identity == result.segments[1].identity


@pytest.mark.parametrize(
    "key,value",
    [
        ("speaker", None),
        ("speaker", ""),
        ("speaker", 3),
        ("speaker", " " * 3),
        ("start", True),
        ("start", "0"),
        ("start", -1),
        ("end", 0),
        ("end", 5),
        ("end", float("nan")),
        ("end", float("inf")),
        ("text", None),
        ("text", 3),
    ],
)
def test_invalid_segments(key, value):
    data = output()
    data["segments"][0][key] = value
    with pytest.raises(AdapterError, match="invalid_output"):
        invoke(data)


@pytest.mark.parametrize(
    "data",
    [
        [],
        {},
        {"text": "x", "segments": []},
        {"text": "missing content", "segments": output()["segments"]},
        dict(output(), language="en"),
        dict(output(), duration=True),
        dict(output(), duration=5),
    ],
)
def test_invalid_envelopes(data):
    with pytest.raises(AdapterError, match="invalid_output"):
        invoke(data)


@pytest.mark.parametrize(
    "payload",
    [b"{", b"{} trailing", b"\xff", b"x" * 262145, b'{"text":"x","text":"y","segments":[]}'],
)
def test_malformed_payload(payload):
    with pytest.raises(AdapterError, match="invalid_output"):
        transcribe(
            OperatorSelection(),
            Request(b"generated", 4, "es"),
            context(),
            "call-001",
            runner=MockRunner(payload),
        )


def test_serialization_and_default_live_lock():
    request = Request(b"generated", 40, "es")
    assert json.loads(request.body) == {"language": "es"}
    assert "--language" not in request.arguments
    assert request.arguments[-4:] == ("--chunking-strategy", "auto", "--format", "json")
    with pytest.raises(AdapterError, match="p1c_required"):
        transcribe(OperatorSelection(), request, context(), "call-001")


@pytest.mark.parametrize("profile", ["demo", "test", "staging", "production", "live_test"])
def test_selection_rejected(profile):
    with pytest.raises(AdapterError, match="selection_rejected"):
        OperatorSelection(profile=profile)


@pytest.mark.parametrize("profile", ["demo", "test", "local_dev", "staging", "production"])
def test_shared_settings_reject_cli(profile):
    field = "local_dev_adapter_shape" if profile == "local_dev" else "transcriber_adapter"
    with pytest.raises(ValueError, match=field):
        Settings(_env_file=None, app_profile=profile, transcriber_adapter="openai_cli_local")


@pytest.mark.parametrize("duration", [0, -1, 91, True, float("nan"), float("inf")])
def test_invalid_input(duration):
    with pytest.raises(AdapterError, match="invalid_input"):
        Request(b"generated", duration, "en")


def test_failure_mapping_is_content_free():
    class Failing:
        def run(self, request):
            raise RuntimeError("private content credential media path")

    with pytest.raises(AdapterError, match=r"^process_failed$"):
        transcribe(
            OperatorSelection(),
            Request(b"generated", 4, "es"),
            context(),
            "call-001",
            runner=Failing(),
        )


@pytest.fixture(autouse=True)
def forbid_processes(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("unit tests must not spawn")

    monkeypatch.setattr("subprocess.Popen", forbidden)


def test_private_primitive_cannot_address_provider():
    from scripts.p1.cli_process import _execute

    with pytest.raises(AdapterError, match="p1c_required"):
        _execute(
            Path("/unavailable"),
            Request(b"generated", 1, "en"),
            "dummy",
            endpoint="https://api.openai.com/v1",
        )


def test_operator_offline_and_live_lock(monkeypatch, capsys):
    from scripts.p1.operator import main

    args = ["operator", "--profile", "local_dev", "--transport", "openai_cli_local"]
    monkeypatch.setattr("sys.argv", args)
    assert main() == 2
    assert "p1c_required" in capsys.readouterr().out
    monkeypatch.setattr("sys.argv", [*args, "--offline"])
    assert main() == 0
    assert "mocked_cli" in capsys.readouterr().out


@pytest.mark.parametrize(
    "code",
    [
        "timeout",
        "cancelled",
        "output_overflow",
        "spawn_failed",
        "stdin_failed",
        "process_failed",
        "cleanup_failed",
        "tool_rejected",
    ],
)
def test_fake_runner_typed_failures(code):
    class Failing:
        def run(self, request):
            raise AdapterError(code)

    with pytest.raises(AdapterError, match=code):
        transcribe(
            OperatorSelection(),
            Request(b"generated", 1, "en"),
            context(),
            "call-001",
            runner=Failing(),
        )
