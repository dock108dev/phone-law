"""Synthetic admission checks: no process, credential acquisition or network."""

import io
import time
import wave
from dataclasses import asdict

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


@pytest.mark.parametrize("failure", ["credential", "timeout", "malformed", "success"])
def test_dispatch_order_retained_debit_and_cleanup(probe, monkeypatch, failure):
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
        return "dummy"

    @contextmanager
    def tunnel():
        yield SimpleNamespace(server_address=("127.0.0.1", 1))

    def dispatch(*args, **kwargs):
        assert campaign.state()[1] == "dispatched"
        if failure == "timeout":
            raise p.AdapterError("timeout")
        if failure == "malformed":
            return b"invalid"
        return b'{"text":"Hello","segments":[{"start":0,"end":1,"speaker":"A","text":"Hello"}]}'

    monkeypatch.setattr(p, "terminal_credential", credential)
    monkeypatch.setattr(p, "fixed_tunnel", tunnel)
    monkeypatch.setattr(p, "_execute", dispatch)
    result = p.run(path)
    assert result["media_removed"]
    assert campaign.state()[0].requests == 3
    assert campaign.state()[0].micro_usd == 560000
    assert (campaign.root / (p.SCOPE + ".used")).exists()
    assert campaign.state()[1] == ("reserved" if failure == "credential" else "dispatched")
    assert result["verified_billed_micro_usd"] is None
    if failure == "success":
        assert result["status"] == "observed_local_cli_success"
    else:
        assert result["status"] == "stopped_debit_retained"
