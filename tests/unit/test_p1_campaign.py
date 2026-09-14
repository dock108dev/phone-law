"""Isolated synthetic campaign tests; never use owner state or provider credentials."""

import io
import os
import wave
from dataclasses import asdict

import pytest

from scripts.p1 import admission as a
from scripts.p1 import campaign as c


@pytest.fixture
def campaign(tmp_path):
    root = tmp_path.resolve() / "state"
    root.mkdir(mode=0o700)
    return c.Campaign(root)


def record(campaign, debit=None, unknown=None):
    debit = debit or c.Debit()
    evidence = campaign.root / "historical-evidence.json"
    if not evidence.exists():
        c.create_private(evidence, b"synthetic historical evidence\n")
    return c.encoded(
        {
            "schema": 1,
            "campaign": c.CAMPAIGN,
            "status": "reconciled",
            "evidence": [{"path": str(evidence), "sha256": c.digest(evidence.read_bytes())}],
            "debit": asdict(debit),
            "unknown": unknown or [],
            "reviewer": "synthetic-test",
        }
    )


def initialize(campaign, debit=None):
    debit = debit or c.Debit()
    campaign.initialize(record(campaign, debit))


def complete(campaign, debit=None):
    debit = debit or c.Debit(1, 90_000_000, 4 * 1024 * 1024, 333333)
    with campaign.locked():
        campaign.reserve(debit, "a" * 64)
        campaign.transition("dispatched")
        campaign.transition("completed")


def test_first_use_and_missing_initialized_state(campaign):
    with pytest.raises(c.AdmissionError, match="first_initialization"):
        campaign.state()
    with pytest.raises(c.AdmissionError):
        campaign.initialize(c.encoded({}))
    assert not campaign.marker.exists()
    initialize(campaign)
    campaign.ledger.unlink()
    with pytest.raises(c.AdmissionError, match="initialized_state_missing"):
        campaign.state()
    with pytest.raises(c.AdmissionError, match="already_initialized"):
        initialize(campaign)


def test_legacy_state_never_overwritten(campaign):
    c.create_private(campaign.ledger, b'{"state":"reserved"}\n')
    with pytest.raises(c.AdmissionError, match="already_initialized"):
        initialize(campaign)
    assert campaign.ledger.read_bytes() == b'{"state":"reserved"}\n'


def test_unresolved_history_and_bound_evidence(campaign):
    with pytest.raises(c.AdmissionError, match="history_unresolved"):
        campaign.initialize(record(campaign, unknown=["lost response"]))
    assert not campaign.marker.exists()
    initialize(campaign, c.Debit(2, 20_000_000, 1000, 1_000_000))
    complete(campaign)
    assert campaign.state()[0].requests == 3
    (campaign.root / "historical-evidence.json").write_bytes(b"changed")
    with pytest.raises(c.AdmissionError, match="evidence_changed"):
        campaign.state()


def test_exact_caps_restart_and_source_independence(campaign):
    initialize(campaign)
    for _ in range(6):
        complete(c.Campaign(campaign.root))
    total = campaign.state()[0]
    assert total == c.Debit(6, 540_000_000, 24 * 1024 * 1024, 1_999_998)
    with pytest.raises(c.AdmissionError, match="capacity_exceeded"):
        complete(c.Campaign(campaign.root))


@pytest.mark.parametrize(
    "debit",
    [c.Debit(1, 1, 1, 2_000_000), c.Debit(1, 90_000_000, 1, 1), c.Debit(1, 1, 4 * 1024 * 1024, 1)],
)
def test_independent_cap_boundaries(campaign, debit):
    initialize(campaign, c.Debit(5, 450_000_000, 20 * 1024 * 1024, 0))
    complete(campaign, debit)
    with pytest.raises(c.AdmissionError):
        complete(campaign, c.Debit(1, 1, 1, 1))


@pytest.mark.parametrize("value", [True, 1.0, -1, 2_000_001])
def test_money_requires_exact_bounded_integer(value):
    with pytest.raises(c.AdmissionError):
        c.Debit(micro_usd=value)


@pytest.mark.parametrize(
    "mutation", ["partial", "whole_line", "head", "permissions", "symlink", "marker"]
)
def test_corruption_and_unsafe_state(campaign, mutation):
    initialize(campaign)
    complete(campaign)
    if mutation == "partial":
        campaign.ledger.write_bytes(campaign.ledger.read_bytes()[:-1])
    elif mutation == "whole_line":
        campaign.ledger.write_bytes(
            b"\n".join(campaign.ledger.read_bytes().splitlines()[:-1]) + b"\n"
        )
    elif mutation == "head":
        campaign.head.write_bytes(b"bad")
    elif mutation == "permissions":
        campaign.ledger.chmod(0o644)
    elif mutation == "marker":
        campaign.marker.unlink()
    else:
        saved = campaign.ledger.with_suffix(".saved")
        campaign.ledger.rename(saved)
        campaign.ledger.symlink_to(saved)
    with pytest.raises((c.AdmissionError, OSError)):
        campaign.state()


def test_lock_required_and_exclusive(campaign):
    initialize(campaign)
    with pytest.raises(c.AdmissionError, match="lock_required"):
        campaign.reserve(c.Debit(1, 1, 1, 1), "a" * 64)
    with (
        campaign.locked(),
        pytest.raises(c.AdmissionError, match="campaign_busy"),
        c.Campaign(campaign.root).locked(),
    ):
        pytest.fail("second admission acquired lock")


@pytest.mark.parametrize(
    "stage", ["credential", "timeout", "cancelled", "malformed", "lost_response", "completed"]
)
def test_admission_order_and_failure_holds(campaign, stage):
    initialize(campaign)
    steps = []

    def validate():
        steps.append("validate")
        return a.Preflight((), (), None, "a" * 64), c.Debit(1, 1, 1, 1), "a" * 64

    def credential():
        assert campaign.state()[1] == "reserved"
        steps.append("credential")
        if stage == "credential":
            raise RuntimeError("credential")
        return "dummy"

    def dispatch(key):
        assert key == "dummy" and campaign.state()[1] == "dispatched"
        steps.append("dispatch")
        if stage != "completed":
            raise RuntimeError(stage)
        return b"validated"

    if stage == "completed":
        assert a._admit(campaign, validate, credential, dispatch) == b"validated"
        assert campaign.state()[1] == ""
    else:
        with pytest.raises(RuntimeError):
            a._admit(campaign, validate, credential, dispatch)
        with pytest.raises(c.AdmissionError, match="unresolved_debit"):
            complete(c.Campaign(campaign.root))
    assert steps[:2] == ["validate", "credential"]
    assert campaign.state()[0].requests == 1


@pytest.mark.parametrize("point", ["journal", "head_replace", "directory_sync"])
def test_crash_during_transition(campaign, monkeypatch, point):
    initialize(campaign)
    original = c.create_private

    def fail_head(path, raw):
        raise OSError("simulated power loss")

    if point == "journal":
        monkeypatch.setattr(c, "create_private", fail_head)
    elif point == "head_replace":
        monkeypatch.setattr(c.os, "replace", fail_head)
    else:

        def fail_sync(path):
            raise OSError("simulated power loss")

        monkeypatch.setattr(c, "sync_directory", fail_sync)
    with campaign.locked(), pytest.raises(OSError):
        campaign.reserve(c.Debit(1, 1, 1, 1), "a" * 64)
    monkeypatch.setattr(c, "create_private", original)
    with pytest.raises(c.AdmissionError, match="interrupted_or_corrupt"):
        c.Campaign(campaign.root).state()


def test_preflight_no_mutation_credentials_or_process(campaign, monkeypatch):
    initialize(campaign)
    before = {p.name: p.read_bytes() for p in campaign.root.iterdir()}

    def forbidden(*args, **kwargs):
        pytest.fail("credential read or process start")

    monkeypatch.setattr("subprocess.Popen", forbidden)
    monkeypatch.setattr(os, "read", forbidden)
    for _ in range(2):
        result = a.preflight(campaign, a.Inputs())
        assert not result.ready
        assert "pricing_upper_bound_unestablished" in result.engineering
        assert "credential_descriptor_unavailable" in result.account
    with pytest.raises(c.AdmissionError, match="preflight_rejected"):
        a.execute(campaign, a.Inputs())
    assert before == {p.name: p.read_bytes() for p in campaign.root.iterdir()}


def test_rejected_admission_never_debits(campaign):
    initialize(campaign)

    def forbidden():
        pytest.fail("credential accessed")

    with pytest.raises(c.AdmissionError, match="preflight_rejected"):
        a._admit(
            campaign,
            lambda: (a.Preflight(("rejected",), (), None, "a" * 64), c.Debit(1, 1, 1, 1), "a" * 64),
            forbidden,
            lambda key: b"",
        )
    assert campaign.state()[0] == c.Debit()


def test_generated_silence_and_forged_provenance(campaign):
    media = io.BytesIO()
    with wave.open(media, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\0\0" * 16000)
    path, proof = campaign.root / "audio.wav", campaign.root / "provenance.json"
    c.create_private(path, media.getvalue())
    c.create_private(
        proof,
        c.encoded(
            {"generator": "p1c-silence-v1", "sha256": c.digest(media.getvalue()), "language": "en"}
        ),
    )
    assert a.generated_input(a.Inputs(media=path, provenance=proof)).duration == 1
    path.write_bytes(media.getvalue()[:-1] + b"x")
    with pytest.raises(c.AdmissionError):
        a.generated_input(a.Inputs(media=path, provenance=proof))


@pytest.mark.parametrize(
    "change,code",
    [
        ("expired", "approval_expired"),
        ("source", "approval_identity_or_scope"),
        ("example", "approval_example"),
    ],
)
def test_approval_expiry_source_and_examples(campaign, change, code):
    approval = {
        "campaign": c.CAMPAIGN,
        "model": a.MODEL,
        "source_sha256": "a" * 64,
        "contract_sha256": c.digest((a.ROOT / "scripts/p1/cli-contract.json").read_bytes()),
        "scope": "P1F-generated-only",
        "max_requests": 6,
        "max_micro_usd": 2_000_000,
        "max_microseconds": 540_000_000,
        "max_bytes": 24 * 1024 * 1024,
        "expires_at": 110,
        "reviewer": "test",
        "example": False,
    }
    if change == "expired":
        approval["expires_at"] = 99
    elif change == "source":
        approval["source_sha256"] = "b" * 64
    else:
        approval["example"] = True
    path = campaign.root / "approval.json"
    c.create_private(path, c.encoded(approval))
    with pytest.raises(c.AdmissionError, match=code):
        a._approval(a.Inputs(approval=path), "a" * 64, 100)


def test_account_evidence_is_not_approval_booleans(campaign, monkeypatch):
    initialize(campaign)
    monkeypatch.setattr(
        a,
        "_approval",
        lambda *args: {
            "project_id": "proj_test",
            "organization_id": "org-test",
            "firm_owned": True,
        },
    )
    result = a.preflight(campaign, a.Inputs())
    assert all(
        category + "_evidence_required" in result.account for category in a.ACCOUNT_CATEGORIES
    )


def test_credential_availability_reads_metadata_only(campaign):
    initialize(campaign)
    read_fd, write_fd = os.pipe()
    try:
        os.write(write_fd, b"dummy")
        result = a.preflight(campaign, a.Inputs(key_fd=read_fd))
        assert "credential_descriptor_unavailable" not in result.account
        assert os.read(read_fd, 5) == b"dummy"
        assert campaign.state()[0].requests == 0
    finally:
        os.close(read_fd)
        os.close(write_fd)
