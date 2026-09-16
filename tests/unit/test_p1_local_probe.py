"""Synthetic admission checks: no process, credential acquisition or network."""

import io
import json
import time
import wave
from dataclasses import asdict
from pathlib import Path

import pytest

from scripts.p1 import campaign as c
from scripts.p1 import local_probe as p


@pytest.fixture
def probe(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    root.chmod(0o700)
    monkeypatch.setattr(p, "DIRECTORY", root)
    raw = io.BytesIO()
    with wave.open(raw, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\0\0" * 16000 * 11)
    media = raw.getvalue()
    receipt = {
        "scope": p.SCOPE,
        "text": p.TEXT,
        "voice": p.VOICE,
        "rate": p.RATE,
        "language": "en",
        "sha256": c.digest(media),
        "bytes": len(media),
        "duration": 11,
    }
    c.create_private(root / "generated.wav", media)
    c.create_private(root / "sample.json", c.encoded(receipt))
    proof = root / "owner.txt"
    c.create_private(proof, b"Synthetic owner decisions; not live authorization.")
    campaign = c.Campaign(root)
    campaign.initialize(
        c.encoded(
            {
                "schema": 1,
                "campaign": c.CAMPAIGN,
                "status": "reconciled",
                "evidence": [{"path": str(proof), "sha256": c.digest(proof.read_bytes())}],
                "debit": asdict(c.Debit(2, 20_000_000, 1000, 500_000)),
                "unknown": [],
                "reviewer": "test",
            }
        )
    )
    monkeypatch.setattr(p, "implementation_identity", lambda: "a" * 64)
    binary = root / "binary"
    c.create_private(binary, b"test")
    monkeypatch.setattr(
        p,
        "load_contract",
        lambda: {"relative_install_path": str(binary), "binary_sha256": c.digest(b"test")},
    )
    approval = {
        "scope": p.SCOPE,
        "campaign": c.CAMPAIGN,
        "model": p.MODEL,
        "source_sha256": "a" * 64,
        "media_sha256": c.digest(media),
        "contract_sha256": c.digest((p.ROOT / "scripts/p1/cli-contract.json").read_bytes()),
        "requests": 1,
        "automatic_retries": 0,
        "estimate_micro_usd": 60000,
        "authorize_estimated_request_without_guaranteed_2usd_ceiling": True,
        "accept_same_origin_redirect_gets": True,
        "accept_unverified_physical_request_count": True,
        "project_key_matches_selected_project": True,
        "example": False,
        "account_kind": "personal_development",
        "project_id": "proj_test",
        "reviewer": "test",
        "issued_at": int(time.time()),
        "expires_at": int(time.time()) + 3600,
        "owner_decision": {"path": str(proof), "sha256": c.digest(proof.read_bytes())},
    }
    path = root / "approval.json"
    c.create_private(path, c.encoded(approval))
    return campaign, path, approval


def test_personal_project_allowed_preserves_prior_debit(probe):
    campaign, path, _ = probe
    _, _, debit = p.validate(campaign, path)
    assert debit.requests == 1 and debit.micro_usd == 60000
    assert campaign.state()[0] == c.Debit(2, 20_000_000, 1000, 500_000)


@pytest.mark.parametrize(
    "field,value",
    [
        ("authorize_estimated_request_without_guaranteed_2usd_ceiling", False),
        ("accept_same_origin_redirect_gets", False),
        ("requests", 2),
        ("automatic_retries", 1),
        ("source_sha256", "b" * 64),
        ("media_sha256", "b" * 64),
        ("expires_at", 1),
        ("account_kind", "production"),
        ("example", True),
        ("project_id", "bad\nvalue"),
    ],
)
def test_rejects_missing_decisions_and_scope_expansion(probe, field, value):
    campaign, path, approval = probe
    approval[field] = value
    path.write_bytes(c.encoded(approval))
    with pytest.raises(c.AdmissionError):
        p.validate(campaign, path)
    assert campaign.state()[0].requests == 2


def test_media_changed(probe):
    campaign, path, _ = probe
    (p.DIRECTORY / "generated.wav").write_bytes(b"recording")
    with pytest.raises((c.AdmissionError, wave.Error, EOFError)):
        p.validate(campaign, path)


def test_one_probe_only_even_after_success(probe):
    campaign, path, _ = probe
    c.create_private(campaign.root / (p.SCOPE + ".used"), b"used")
    with pytest.raises(c.AdmissionError, match="already_attempted"):
        p.validate(campaign, path)


def test_ambiguous_hold_and_campaign_capacity(probe):
    campaign, path, _ = probe
    with campaign.locked():
        campaign.reserve(c.Debit(1, 1, 1, 1), "a" * 64)
    with pytest.raises(c.AdmissionError, match="unresolved_debit"):
        p.validate(campaign, path)


def test_no_credential_without_local_terminal(monkeypatch):
    monkeypatch.setattr(p.sys.stdin, "isatty", lambda: False)
    with pytest.raises(c.AdmissionError, match="owner_local_terminal"):
        p.run(p.DIRECTORY / "missing.json")


def test_usage_never_retains_provider_strings():
    assert p.numeric_usage({"seconds": 11, "secret": "abc", "text_tokens": "abc"}) == {
        "seconds": 11,
        "text_tokens": None,
    }


@pytest.mark.parametrize(
    "failure",
    [
        "credential",
        "expired_during_entry",
        "timeout",
        "malformed",
        "success",
        "cleanup",
        "timeout_cleanup",
        "unexpected",
        "outcome_write",
    ],
)
def test_dispatch_order_retained_debit_and_cleanup(probe, monkeypatch, caplog, failure):
    from contextlib import contextmanager
    from types import SimpleNamespace

    campaign, path, _ = probe
    monkeypatch.setattr(p.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(p, "Campaign", lambda root: campaign)
    monkeypatch.setattr(p, "verified_executable", lambda: path)

    def credential():
        assert campaign.state()[0].requests == 3
        assert campaign.state()[1] == "reserved"
        if failure == "credential":
            raise p.AdmissionError("credential_unavailable")
        if failure == "expired_during_entry":
            record = c.decode(c.read_private(path))
            record["expires_at"] = 1
            path.write_bytes(c.encoded(record))
        return "dummy"

    @contextmanager
    def tunnel():
        yield SimpleNamespace(server_address=("127.0.0.1", 1))

    def dispatch(*args, **kwargs):
        assert campaign.state()[1] == "dispatched"
        if failure in {"timeout", "timeout_cleanup"}:
            raise p.AdapterError("timeout")
        if failure == "unexpected":
            raise RuntimeError("private-failure-content")
        if failure == "malformed":
            return b"invalid"
        return b'{"text":"Hello","segments":[{"start":0,"end":1,"speaker":"A","text":"Hello"}]}'

    monkeypatch.setattr(p, "terminal_credential", credential)
    monkeypatch.setattr(p, "fixed_tunnel", tunnel)
    monkeypatch.setattr(p, "_execute", dispatch)
    if failure in {"cleanup", "timeout_cleanup"}:
        unlink = Path.unlink

        def failed_cleanup(target, *args, **kwargs):
            if target == p.DIRECTORY / "generated.wav":
                raise PermissionError("private-failure-content")
            return unlink(target, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", failed_cleanup)
    if failure == "outcome_write":
        create = p.create_private

        def failed_write(target, raw):
            if target.name.startswith("outcome-"):
                raise OSError("private-failure-content")
            return create(target, raw)

        monkeypatch.setattr(p, "create_private", failed_write)
        monkeypatch.setattr(p.sys, "argv", ["probe", "run", "--approval", str(path)])
        assert p.main() == 2
        assert campaign.state()[1] == "dispatched"
        assert campaign.state()[0].requests == 3
        assert "probe_outcome_write_failed" in caplog.text
        assert "private-failure-content" not in caplog.text
        return
    result = p.run(path)
    assert result["media_removed"] == (failure not in {"cleanup", "timeout_cleanup"})
    saved = list(p.DIRECTORY.glob("outcome-*.json"))
    assert len(saved) == 1
    assert json.loads(saved[0].read_text()) == result
    assert "private-failure-content" not in caplog.text
    assert campaign.state()[0].requests == 3
    assert campaign.state()[0].micro_usd == 560000
    assert (campaign.root / (p.SCOPE + ".used")).exists()
    assert campaign.state()[1] == (
        "reserved" if failure in ("credential", "expired_during_entry") else "dispatched"
    )
    if failure == "expired_during_entry":
        assert result["provider_dispatch_attempts"] == 0
    assert result["verified_billed_micro_usd"] is None
    if failure in {"cleanup", "timeout_cleanup"}:
        assert result["status"] == "cleanup_failed"
        assert result["execution_status"] == (
            "observed_local_cli_success" if failure == "cleanup" else "stopped_debit_retained"
        )
        if failure == "timeout_cleanup":
            assert result["code"] == "timeout"
            assert "probe_execution_failed" in caplog.text
        assert "probe_media_cleanup_failed" in caplog.text
    elif failure == "success":
        assert result["status"] == "observed_local_cli_success"
    else:
        assert result["status"] == "stopped_debit_retained"


def test_hidden_input_never_falls_back_to_echo(monkeypatch):
    import warnings

    def fallback(prompt):
        warnings.warn("synthetic terminal unavailable", p.getpass.GetPassWarning, stacklevel=2)
        pytest.fail("echo fallback reached")

    monkeypatch.setattr(p.getpass, "getpass", fallback)
    with pytest.raises(c.AdmissionError, match="hidden_terminal_required"):
        p.terminal_credential()


@pytest.mark.parametrize("issued,expires", [(1, 9999999999), (9999999999, 99999999999)])
def test_execution_window_cannot_be_extended(probe, issued, expires):
    campaign, path, record = probe
    record.update(issued_at=issued, expires_at=expires)
    path.write_bytes(c.encoded(record))
    with pytest.raises(c.AdmissionError, match="expiry"):
        p.validate(campaign, path)
    assert campaign.state()[0].requests == 2


@pytest.fixture
def resume(probe, monkeypatch):
    from scripts.p1 import probe_resume as r

    campaign, _, approval = probe
    owner = p.DIRECTORY / "owner-approval-20260913.json"
    c.create_private(
        owner,
        c.encoded(
            {
                "scope": p.SCOPE,
                "owner_reply": "approved, no additional requests",
                "estimated_attempt_approved": True,
                "billing_and_redirect_limitations_accepted": True,
                "additional_colacci_requests": 0,
            }
        ),
    )
    historical = p.DIRECTORY / "history.json"
    c.create_private(historical, b"history")
    c.create_private(p.DIRECTORY / "backup.json", b"history")
    manifest = {
        "source_sha256": "a" * 64,
        "runtime_versions": r.runtime_versions(),
        "python_sha256": c.digest(r.Path(r.sys.executable).resolve().read_bytes()),
        "files": {},
        "private_files": {owner.name: c.digest(owner.read_bytes())},
        "media_sha256": approval["media_sha256"],
        "ledger_sha256": c.digest(campaign.state()[2]),
        "historical_evidence": [
            {"path": str(historical), "backup": "backup.json", "sha256": c.digest(b"history")}
        ],
    }
    c.create_private(p.DIRECTORY / "prepared.json", c.encoded(manifest))
    monkeypatch.setattr(r, "implementation_identity", lambda: "a" * 64)
    monkeypatch.setattr(r, "load_contract", p.load_contract)
    monkeypatch.setattr(r, "Campaign", lambda root: campaign)
    return r, campaign, manifest, historical


def test_resume_fresh_binding_preserves_decision_and_ledger(resume):
    r, campaign, manifest, _ = resume
    before = campaign.state()[2]
    path = r.bind("proj_private", manifest)
    record = p.approval_record(path, p.sample()[0])
    assert record["expires_at"] - record["issued_at"] == 3600
    assert record["project_id"] == "proj_private"
    assert record["owner_decision"]["path"].endswith("owner-approval-20260913.json")
    assert campaign.state()[2] == before


@pytest.mark.parametrize("change", ["source", "runtime", "media", "owner", "history", "ledger"])
def test_resume_blocks_drift_before_entry(resume, monkeypatch, change):
    r, campaign, _, historical = resume
    if change == "source":
        monkeypatch.setattr(r, "implementation_identity", lambda: "b" * 64)
    elif change == "runtime":
        monkeypatch.setattr(r, "runtime_versions", lambda: {})
    elif change == "media":
        (p.DIRECTORY / "generated.wav").write_bytes(b"changed")
    elif change == "owner":
        (p.DIRECTORY / "owner-approval-20260913.json").write_bytes(b"changed")
    elif change == "history":
        historical.write_bytes(b"changed")
    else:
        with campaign.locked():
            campaign.reserve(c.Debit(1, 1, 1, 1), "a" * 64)
    with pytest.raises((c.AdmissionError, wave.Error, EOFError)):
        r.check()
    assert not list(p.DIRECTORY.glob("execution-approval-*"))


def test_resume_restores_only_missing_history_without_ledger_change(resume):
    r, campaign, manifest, historical = resume
    before = campaign.state()[2]
    historical.unlink()
    assert r.check() == manifest
    assert historical.read_bytes() == b"history"
    assert campaign.state()[2] == before


@pytest.mark.parametrize("mode", ["run", "preflight"])
def test_command_failure_never_invents_zero_dispatch_after_run(monkeypatch, capsys, mode):
    def fail(*args, **kwargs):
        raise OSError("private-failure-content")

    monkeypatch.setattr(p, "run", fail)
    monkeypatch.setattr(p, "Campaign", fail)
    monkeypatch.setattr(p.sys, "argv", ["probe", mode, "--approval", "invented.json"])
    assert p.main() == 2
    result = json.loads(capsys.readouterr().out)
    assert result["provider_requests"] == (None if mode == "run" else 0)
    assert result["status"] == ("execution_unconfirmed" if mode == "run" else "blocked")


def test_reservation_write_failure_keeps_durable_state_unknown(probe, monkeypatch):
    campaign, path, _ = probe
    monkeypatch.setattr(p.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(p, "Campaign", lambda root: campaign)
    monkeypatch.setattr(p, "verified_executable", lambda: path)

    def interrupted_reservation(*args):
        raise OSError("simulated fsync failure")

    monkeypatch.setattr(campaign, "reserve", interrupted_reservation)
    monkeypatch.setattr(p, "terminal_credential", lambda: pytest.fail("credential entry reached"))
    result = p.run(path)
    assert result["status"] == "reservation_state_unconfirmed"
    assert result["provider_dispatch_attempts"] == 0
    assert result["media_removed"]
