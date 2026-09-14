"""Network-free P1 cap, crash, credential, contract and transport verification."""

from __future__ import annotations

import io
import json
import os
import wave
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from scripts.p1 import controlled_openai as p1


def audio(case: str = "english", seconds: int = 2) -> p1.Audio:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\0\0" * 16000 * seconds)
    return p1.inspect_audio(case, "es" if case == "spanish" else "en", buffer.getvalue())


def response(a: p1.Audio) -> bytes:
    text = "jardín bicicleta" if a.language == "es" else "garden bicycle"
    return json.dumps(
        {
            "text": text,
            "duration": a.seconds,
            "language": a.language,
            "segments": [{"start": 0, "end": a.seconds, "text": text}],
        }
    ).encode()


def approval() -> dict[str, Any]:
    return {
        "campaign": p1.CAMPAIGN,
        "model": p1.MODEL,
        "source_sha256": p1.source_identity(),
        "firm_owned_project_confirmed": True,
        "project_scoped_key_confirmed": True,
        "transcription_permission_confirmed": True,
        "billing_active_confirmed": True,
        "terms_reviewed": True,
        "data_controls_reviewed": True,
        "data_sharing_disabled_confirmed": True,
        "generated_only_authorized": True,
        "global_endpoint_approved": True,
        "price_per_minute_micro_usd": 6000,
        "max_requests": 6,
        "max_spend_micro_usd": 2_000_000,
        "project_id": "proj_synthetic",
        "organization_id": "org-synthetic",
        "ownership_evidence_reference": "synthetic",
        "terms_evidence_reference": "synthetic",
        "data_controls_evidence_reference": "synthetic",
        "expires_at": 2000,
    }


def test_preflight_never_constructs_client(monkeypatch: pytest.MonkeyPatch) -> None:
    client = Mock(side_effect=AssertionError("network forbidden"))
    monkeypatch.setattr(p1.http.client, "HTTPSConnection", client)
    assert p1.preflight(approval(), True, 1000) == []
    assert "ephemeral_key_descriptor" in p1.preflight({}, False, 1000)
    client.assert_not_called()


@pytest.mark.parametrize("field", list(approval()))
def test_every_approval_field_required(field: str) -> None:
    record = approval()
    del record[field]
    assert p1.preflight(record, True, 1000)


@pytest.mark.parametrize("value", [0, 1000, 100000, float("nan"), True, "2000"])
def test_invalid_expiry(value: Any) -> None:
    record = approval()
    record["expires_at"] = value
    assert "fresh_approval_expiry" in p1.preflight(record, True, 1000)


def test_preflight_boolean_not_integer() -> None:
    record = approval()
    record["terms_reviewed"] = 1
    assert "terms_reviewed" in p1.preflight(record, True, 1000)


@pytest.mark.parametrize(("case", "seconds"), [("english", 2), ("spanish", 2), ("long", 40)])
def test_three_contract_cases(tmp_path: Path, case: str, seconds: int) -> None:
    a = audio(case, seconds)
    ledger = p1.Ledger(tmp_path / "ledger")
    try:
        result = p1.transcribe(a, ledger, lambda a: (200, response(a)))
        assert result["language_matches"] and result["timestamps_valid"]
        assert result["billed_cost_usd"] is None
        assert "text" not in result
    finally:
        ledger.close()


def test_global_six_request_limit_survives_reopening(tmp_path: Path) -> None:
    path = tmp_path / "ledger"
    transport = Mock(side_effect=lambda a: (200, response(a)))
    for _ in range(6):
        ledger = p1.Ledger(path)
        p1.transcribe(audio(), ledger, transport)
        ledger.close()
    ledger = p1.Ledger(path)
    with pytest.raises(p1.BlockedError, match="request_limit"):
        p1.transcribe(audio(), ledger, transport)
    ledger.close()
    assert transport.call_count == 6


@pytest.mark.parametrize("status", [301, 400, 401, 403, 429, 500, 503])
def test_failures_are_debited_not_retried(tmp_path: Path, status: int) -> None:
    path = tmp_path / "ledger"
    ledger = p1.Ledger(path)
    transport = Mock(return_value=(status, b"sensitive raw provider error"))
    with pytest.raises(p1.BlockedError, match="provider_http_failure"):
        p1.transcribe(audio(), ledger, transport)
    ledger.close()
    assert transport.call_count == 1
    assert p1.MAX_RETRIES == 0
    with pytest.raises(p1.BlockedError, match="ledger_unresolved_request"):
        p1.Ledger(path)
    assert b"sensitive" not in path.read_bytes()


def test_transport_exception_sanitized_and_crash_conservative(tmp_path: Path) -> None:
    path = tmp_path / "ledger"
    ledger = p1.Ledger(path)
    transport = Mock(side_effect=TimeoutError("secret response"))
    with pytest.raises(p1.BlockedError, match=r"^provider_transport_failure$"):
        p1.transcribe(audio(), ledger, transport)
    ledger.close()
    assert json.loads(path.read_text())["micro_usd"] == 6000
    with pytest.raises(p1.BlockedError, match="ledger_unresolved_request"):
        p1.Ledger(path)


@pytest.mark.parametrize(
    ("constant", "value", "code"),
    [
        ("MAX_SPEND_MICRO_USD", 5999, "spending_limit"),
        ("MAX_TOTAL_SECONDS", 1, "total_duration_limit"),
        ("MAX_TOTAL_BYTES", 44, "total_byte_limit"),
    ],
)
def test_aggregate_limits_before_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, constant: str, value: int, code: str
) -> None:
    monkeypatch.setattr(p1, constant, value)
    ledger = p1.Ledger(tmp_path / "ledger")
    transport = Mock()
    with pytest.raises(p1.BlockedError, match=code):
        p1.transcribe(audio(), ledger, transport)
    ledger.close()
    transport.assert_not_called()


@pytest.mark.parametrize(("case", "seconds"), [("english", 0), ("english", 91), ("long", 30)])
def test_duration_rejected(case: str, seconds: int) -> None:
    with pytest.raises(p1.BlockedError):
        audio(case, seconds)


def test_exact_duration_boundary_and_price_roundup() -> None:
    assert audio(seconds=90).seconds == 90
    assert p1.reservation(audio(seconds=60)) == 6000
    assert p1.reservation(audio(seconds=61)) == 12000
    assert p1.MAX_REQUESTS * p1.reservation(audio(seconds=90)) == 72000


def test_size_format_and_case_limits() -> None:
    with pytest.raises(p1.BlockedError, match="audio_byte_limit"):
        p1.inspect_audio("english", "en", bytes(p1.MAX_BYTES + 1))
    with pytest.raises(p1.BlockedError, match="audio_format"):
        p1.inspect_audio("english", "en", bytes(100))
    with pytest.raises(p1.BlockedError, match="case_not_allowlisted"):
        p1.inspect_audio("client", "en", audio().content)
    with pytest.raises(p1.BlockedError, match="audio_truncated"):
        p1.inspect_audio("english", "en", audio().content[:-100])


@pytest.mark.parametrize(
    "patch",
    [
        {"text": ""},
        {"text": "unrelated"},
        {"language": "fr"},
        {"duration": float("nan")},
        {"duration": 999},
        {"segments": []},
        {"segments": [{"start": -1, "end": 2, "text": "x"}]},
        {"segments": [{"start": 0, "end": 999, "text": "x"}]},
    ],
)
def test_invalid_response(patch: dict[str, Any]) -> None:
    result = json.loads(response(audio()))
    result.update(patch)
    with pytest.raises(p1.BlockedError):
        p1.validate_response(audio(), json.dumps(result).encode())


def test_response_byte_limit_and_invalid_json() -> None:
    for content in (bytes(p1.MAX_RESPONSE_BYTES + 1), b"bad json"):
        with pytest.raises(p1.BlockedError):
            p1.validate_response(audio(), content)


def test_concurrent_ledger_rejected(tmp_path: Path) -> None:
    path = tmp_path / "ledger"
    ledger = p1.Ledger(path)
    try:
        with pytest.raises(BlockingIOError):
            p1.Ledger(path)
    finally:
        ledger.close()


def test_corrupt_and_symlink_ledgers_rejected(tmp_path: Path) -> None:
    path = tmp_path / "ledger"
    path.write_text("broken\n")
    path.chmod(0o600)
    with pytest.raises(ValueError):
        p1.Ledger(path)
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(OSError):
        p1.Ledger(link)


def test_evidence_immutable_private_and_safe(tmp_path: Path) -> None:
    path = tmp_path / "record.json"
    p1.write_record(path, {"safe": True})
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        p1.write_record(path, {"safe": False})
    assert p1.private_file(path) == path.read_bytes()
    path.chmod(0o644)
    with pytest.raises(p1.BlockedError, match="private_file_permissions"):
        p1.private_file(path)


def test_key_only_from_anonymous_pipe_and_closed() -> None:
    read_fd, write_fd = os.pipe()
    key = "sk-proj-" + "synthetic" * 4
    os.write(write_fd, key.encode())
    os.close(write_fd)
    assert p1.read_key(read_fd) == key
    with pytest.raises(OSError):
        os.fstat(read_fd)


def test_key_file_rejected_and_closed(tmp_path: Path) -> None:
    path = tmp_path / "not-a-credential"
    path.touch()
    fd = os.open(path, os.O_RDONLY)
    with pytest.raises(p1.BlockedError, match="credential_requires_pipe"):
        p1.read_key(fd)
    with pytest.raises(OSError):
        os.fstat(fd)


def test_fixed_transport_contract_no_retry_or_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://invalid.invalid")
    connection = Mock()
    connection.getresponse.return_value.status = 200
    connection.getresponse.return_value.read.return_value = response(audio())
    factory = Mock(return_value=connection)
    monkeypatch.setattr(p1.http.client, "HTTPSConnection", factory)
    assert p1.send(audio(), "synthetic", approval())[0] == 200
    assert factory.call_args.args == ("api.openai.com",)
    assert factory.call_args.kwargs["timeout"] == 45
    args = connection.request.call_args.args
    assert args[:2] == ("POST", "/v1/audio/transcriptions")
    assert b"whisper-1" in args[2] and b"verbose_json" in args[2]
    assert b"chunking_strategy" not in args[2] and b"known_speaker" not in args[2]
    assert args[3]["OpenAI-Project"] == "proj_synthetic"
    connection.request.assert_called_once()
    connection.close.assert_called_once()


def test_invalid_response_stops_remaining_cases(tmp_path: Path) -> None:
    ledger = p1.Ledger(tmp_path / "ledger")
    transport = Mock(return_value=(200, b"{}"))
    with pytest.raises(p1.BlockedError):
        for case, _, _ in p1.CASES:
            p1.transcribe(audio(case, 40), ledger, transport)
    ledger.close()
    assert transport.call_count == 1


def test_descriptor_preflight_does_not_consume_key() -> None:
    read_fd, write_fd = os.pipe()
    try:
        os.write(write_fd, b"synthetic")
        assert p1.key_descriptor_available(read_fd)
        assert os.read(read_fd, 9) == b"synthetic"
        assert not p1.key_descriptor_available(0)
        assert not p1.key_descriptor_available(999999)
    finally:
        os.close(read_fd)
        os.close(write_fd)


def test_cli_zero_request_block(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out = tmp_path / "evidence"
    generator = Mock(side_effect=AssertionError("generation not allowed"))
    sender = Mock(side_effect=AssertionError("network not allowed"))
    monkeypatch.setattr(p1, "generate", generator)
    monkeypatch.setattr(p1, "send", sender)
    monkeypatch.setattr("sys.argv", ["p1", "preflight", "--evidence", str(out)])
    assert p1.main() == 2
    assert json.loads((out / "preflight.json").read_text())["provider_requests"] == 0
    generator.assert_not_called()
    sender.assert_not_called()


@pytest.mark.parametrize("failure", [False, True])
def test_cli_live_mock_cleanup_and_sanitization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: bool
) -> None:
    out = tmp_path / "evidence"
    approval_path = tmp_path / "approval.json"
    record = approval()
    record["expires_at"] = p1.time.time() + 3600
    p1.write_record(approval_path, record)
    monkeypatch.setattr(p1.Path, "home", lambda: tmp_path)
    generated_roots = []

    def generate(root: Path) -> list[p1.Audio]:
        generated_roots.append(root)
        (root / "generated.wav").write_bytes(audio().content)
        return [audio(), audio("spanish"), audio("long", 40)]

    monkeypatch.setattr(p1, "generate", generate)
    sender = Mock(
        side_effect=(
            TimeoutError("sensitive") if failure else lambda a, key, approval: (200, response(a))
        )
    )
    monkeypatch.setattr(p1, "send", sender)
    read_fd, write_fd = os.pipe()
    os.write(write_fd, ("sk-proj-" + "synthetic" * 4).encode())
    os.close(write_fd)
    monkeypatch.setattr(
        "sys.argv",
        [
            "p1",
            "live",
            "--evidence",
            str(out),
            "--approval",
            str(approval_path),
            "--key-fd",
            str(read_fd),
        ],
    )
    assert p1.main() == (2 if failure else 0)
    result = json.loads((out / "outcome.json").read_text())
    assert result["provider_requests"] == (1 if failure else 3)
    assert sender.call_count == result["provider_requests"]
    assert result["generated_media_removed"]
    assert all(not root.exists() for root in generated_roots)
    assert "sensitive" not in (out / "outcome.json").read_text()
    with pytest.raises(OSError):
        os.fstat(read_fd)
