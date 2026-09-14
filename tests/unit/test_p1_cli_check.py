"""Deterministic offline CLI qualification; no provider executable in unit tests."""

import hashlib
from pathlib import Path

import pytest

from scripts.p1 import cli_check


def fake_contract(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, dict[str, bytes]]:
    executable = tmp_path / "openai"
    executable.write_text("deterministic executable identity")
    executable.chmod(0o700)
    outputs = {
        "version": b"openai version 1.15.0\n",
        "root": b"audio:transcriptions --format json --base-url",
        "transcription": (
            b"--file --model gpt-4o-transcribe-diarize --response-format diarized_json "
            b"--language --chunking-strategy auto 30 seconds input language"
        ),
    }
    contract = cli_check.load_contract()
    contract["binary_sha256"] = hashlib.sha256(executable.read_bytes()).hexdigest()
    contract["help_sha256"] = {
        name: hashlib.sha256(value).hexdigest() for name, value in outputs.items()
    }
    monkeypatch.setattr(cli_check, "load_contract", lambda: contract)
    return executable, outputs


def test_supported(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    executable, outputs = fake_contract(monkeypatch, tmp_path)
    calls = []

    def probe(path: Path, args: tuple[str, ...]) -> bytes:
        assert path == executable
        calls.append(args)
        return outputs[next(name for name, value in cli_check.PROBES.items() if value == args)]

    monkeypatch.setattr(cli_check, "_probe", probe)
    result = cli_check.check(executable)
    assert result["provider_requests"] == 0
    assert result["credentials_required"] is False
    assert calls == list(cli_check.PROBES.values())


@pytest.mark.parametrize("case", ["missing", "unapproved", "legacy", "relative"])
def test_rejected_without_execution(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, case: str
) -> None:
    executable, _ = fake_contract(monkeypatch, tmp_path)
    contract = cli_check.load_contract()
    expected = "unapproved_executable"
    if case == "missing":
        executable.unlink()
        expected = "executable_missing_or_unreadable"
    elif case == "legacy":
        # Observed Python SDK command shape, never executed or installed.
        executable.write_text("openai 1.3.7\nusage: openai {api,tools,migrate,grit}\n")
        contract["legacy_sha256"] = hashlib.sha256(executable.read_bytes()).hexdigest()
        expected = "legacy_python_cli_incompatible"
    elif case == "relative":
        executable = Path("openai")
        expected = "absolute_executable_required"
    else:
        executable.write_text("unexpected tool")
    monkeypatch.setattr(cli_check, "_probe", lambda *_: pytest.fail("must not execute"))
    with pytest.raises(cli_check.SetupError, match=expected):
        cli_check.check(executable)


@pytest.mark.parametrize(
    ("name", "replacement", "error"),
    [
        ("version", b"openai version 1.3.7", "version_mismatch"),
        ("transcription", b"legacy api audio.transcriptions.create", "capability_mismatch"),
        ("root", b"audio:transcriptions --format json --base-url changed", "help_contract_changed"),
    ],
)
def test_mismatched_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str, replacement: bytes, error: str
) -> None:
    _, outputs = fake_contract(monkeypatch, tmp_path)
    outputs[name] = replacement
    with pytest.raises(cli_check.SetupError, match=error):
        cli_check.validate_help(outputs, cli_check.load_contract())


@pytest.mark.parametrize(
    ("body", "error"),
    [
        ("exit 2", "help_command_failed"),
        ("while :; do :; done", "help_timeout"),
        ("while :; do printf 'synthetic-diagnostic'; done", "help_output_limit"),
    ],
)
def test_bounded_help_process(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, body: str, error: str
) -> None:
    executable = tmp_path / "fake-help"
    executable.write_text("#!/bin/sh\n" + body + "\n")
    executable.chmod(0o700)
    monkeypatch.setattr(cli_check, "TIMEOUT", 0.2 if error == "help_timeout" else 10.0)
    with pytest.raises(cli_check.SetupError, match=error) as caught:
        cli_check._probe(executable, ("--help",))
    assert "synthetic-diagnostic" not in str(caught.value)


def test_child_environment_is_empty_of_ambient_secrets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-sentinel")
    monkeypatch.setenv("OPENAI_BASE_URL", "invalid-sentinel")
    monkeypatch.setenv("OPENAI_MTLS_CLIENT_KEY_FILE", "/must-not-read")
    executable = tmp_path / "fake-help"
    executable.write_text(
        '#!/bin/sh\n[ -z "$OPENAI_API_KEY$OPENAI_BASE_URL$OPENAI_MTLS_CLIENT_KEY_FILE" ] '
        '|| exit 9\n[ "$PWD" = "$HOME" ] || exit 8\nprintf "isolated"\n'
    )
    executable.chmod(0o700)
    assert cli_check._probe(executable, ("--help",)) == b"isolated"
