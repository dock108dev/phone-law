"""Zero-request snapshot and durable admission; P1F and transport/pricing remain blocked."""

from __future__ import annotations

import io
import os
import time
import wave
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from .campaign import (
    CAMPAIGN,
    AdmissionError,
    Campaign,
    Debit,
    decode,
    digest,
    encoded,
    read_private,
)
from .cli_adapter import MODEL, Request
from .cli_check import load_contract
from .controlled_openai import key_descriptor_available

ROOT = Path(__file__).resolve().parents[2]
ACCOUNT_CLAIMS = {
    "ownership": {"firm_owned": True},
    "credential_scope": {"project_scoped": True, "transcription_allowed": True, "ephemeral": True},
    "billing": {"active": True, "model_access": MODEL},
    "terms": {"current_terms_reviewed": True, "generated_audio_authorized": True},
    "data_controls": {
        "sharing_disabled": True,
        "retention_reviewed": True,
        "residency_reviewed": True,
    },
}
ACCOUNT_CATEGORIES = tuple(ACCOUNT_CLAIMS)


def implementation_identity() -> str:
    paths = sorted(
        p
        for base in (ROOT / "scripts", ROOT / "packages")
        for p in base.rglob("*")
        if p.is_file() and p.suffix in (".py", ".json") and "__pycache__" not in p.parts
    )
    paths += [ROOT / "requirements.lock", ROOT / "pyproject.toml"]
    return digest(encoded({str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in paths}))


@dataclass(frozen=True)
class Inputs:
    approval: Path | None = None
    media: Path | None = None
    provenance: Path | None = None
    key_fd: int | None = None


@dataclass(frozen=True)
class Preflight:
    engineering: tuple[str, ...]
    account: tuple[str, ...]
    remaining: dict[str, int] | None
    source_sha256: str
    reservation_micro_usd: int | None = None

    @property
    def ready(self) -> bool:
        return not self.engineering and not self.account

    def record(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "ready": self.ready,
            "provider_requests": 0,
            "budget_reserved": False,
        }


def generated_input(inputs: Inputs) -> Request:
    if inputs.media is None or inputs.provenance is None:
        raise AdmissionError("generated_input_required")
    raw = read_private(inputs.media, 4 * 1024 * 1024)
    proof = decode(read_private(inputs.provenance))
    # P1C accepts deterministic generated silence only. Authored speech receipts are P1D work.
    if (
        set(proof) != {"generator", "sha256", "language"}
        or proof["generator"] != "p1c-silence-v1"
        or proof["sha256"] != digest(raw)
    ):
        raise AdmissionError("generated_provenance_invalid")
    try:
        with wave.open(io.BytesIO(raw), "rb") as wav:
            count = wav.getnframes()
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getcomptype()) != (
                1,
                2,
                16000,
                "NONE",
            ):
                raise AdmissionError("media_format")
            frames = wav.readframes(count)
            if not 0 < count <= 90 * 16000 or frames != b"\0\0" * count:
                raise AdmissionError("generated_provenance_invalid")
        canonical = io.BytesIO()
        with wave.open(canonical, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(frames)
        if raw != canonical.getvalue():
            raise AdmissionError("media_noncanonical")
        return Request(raw, count / 16000, proof["language"])
    except wave.Error, EOFError:
        raise AdmissionError("media_format") from None


def _approval(inputs: Inputs, identity: str, now: float) -> dict[str, Any]:
    if inputs.approval is None:
        raise AdmissionError("approval_required")
    approval = decode(read_private(inputs.approval))
    expected = {
        "campaign": CAMPAIGN,
        "model": MODEL,
        "source_sha256": identity,
        "contract_sha256": digest((ROOT / "scripts/p1/cli-contract.json").read_bytes()),
        "scope": "P1F-generated-only",
        "max_requests": 6,
        "max_micro_usd": 2_000_000,
        "max_microseconds": 540_000_000,
        "max_bytes": 24 * 1024 * 1024,
    }
    for key, value in expected.items():
        if type(approval.get(key)) is not type(value) or approval[key] != value:
            raise AdmissionError("approval_identity_or_scope")
    expiry = approval.get("expires_at")
    if type(expiry) is not int or not now < expiry <= now + 86400:
        raise AdmissionError("approval_expired")
    if not approval.get("reviewer") or approval.get("example") is not False:
        raise AdmissionError("approval_example_or_unsigned")
    if any(
        type(approval.get(k)) is not str or not approval[k].strip()
        for k in ("project_id", "organization_id")
    ):
        raise AdmissionError("account_identity_required")
    return approval


def snapshot(campaign: Campaign, inputs: Inputs) -> Preflight:
    """Read only: no tool probes, credential bytes, reservation or transcription child."""
    engineering, account = [], []
    identity = implementation_identity()
    remaining = None
    try:
        total, pending, _ = campaign.state()
        remaining = total.remaining()
        if pending:
            engineering.append("unresolved_debit")
        if any(v == 0 for v in remaining.values()):
            engineering.append("capacity_exhausted")
    except AdmissionError as exc:
        engineering.append(str(exc))
    except OSError, ValueError, TypeError, KeyError:
        engineering.append("campaign_state_unavailable_or_invalid")
    request = None
    try:
        request = generated_input(inputs)
        if remaining is not None and (
            len(request.media) > remaining["bytes"]
            or int(request.duration * 1_000_000) > remaining["microseconds"]
        ):
            engineering.append("capacity_exceeded")
    except OSError, ValueError, TypeError, KeyError, AdmissionError:
        engineering.append("generated_input_or_private_paths_invalid")
    try:
        contract = load_contract()
        executable = Path.home() / contract["relative_install_path"]
        info = executable.lstat()
        if (
            executable.is_symlink()
            or info.st_uid != os.getuid()
            or info.st_mode & 0o022
            or not os.access(executable, os.X_OK)
            or digest(executable.read_bytes()) != contract["binary_sha256"]
        ):
            raise AdmissionError("tool_identity_invalid")
    except OSError, ValueError, KeyError, AdmissionError:
        engineering.append("tool_identity_invalid")
    try:
        approval = _approval(inputs, identity, time.time())
        for category in ACCOUNT_CATEGORIES:
            try:
                ref = approval["account_evidence"][category]
                raw = read_private(Path(ref["path"]))
                evidence = decode(raw)
                if (
                    digest(raw) != ref["sha256"]
                    or evidence.get("kind") != "owner_verified_account_evidence"
                    or evidence.get("category") != category
                    or evidence.get("project_id") != approval["project_id"]
                    or evidence.get("organization_id") != approval["organization_id"]
                    or not evidence.get("reviewer")
                    or type(evidence.get("expires_at")) is not int
                    or evidence["expires_at"] <= time.time()
                    or evidence.get("example") is not False
                    or evidence.get("claims") != ACCOUNT_CLAIMS[category]
                ):
                    raise AdmissionError("account_evidence_invalid")
                support = evidence["support"]
                if digest(read_private(Path(support["path"]))) != support["sha256"]:
                    raise AdmissionError("account_evidence_changed")
            except OSError, ValueError, TypeError, KeyError, AdmissionError:
                account.append(category + "_evidence_required")
        if request is not None and approval.get("media_sha256") != digest(request.media):
            engineering.append("approval_media_mismatch")
    except AdmissionError as exc:
        account.append(str(exc))
    except OSError, ValueError, TypeError, KeyError:
        account.append("approval_invalid")
    if not key_descriptor_available(inputs.key_fd):
        account.append("credential_descriptor_unavailable")
    # Reviewed policy facts, deliberately not configurable approval booleans.
    engineering.extend(
        (
            "pricing_upper_bound_unestablished",
            "transport_redirect_boundary_unqualified",
            "live_phase_P1F_required",
        )
    )
    return Preflight(tuple(engineering), tuple(account), remaining, identity)


def preflight(campaign: Campaign, inputs: Inputs) -> Preflight:
    try:
        with campaign.locked():
            return snapshot(campaign, inputs)
    except OSError, AdmissionError:
        result = snapshot(campaign, inputs)
        return replace(result, engineering=(*result.engineering, "campaign_lock_unavailable"))


def _admit(
    campaign: Campaign,
    validate: Callable[[], tuple[Preflight, Debit, str]],
    credential: Callable[[], str],
    dispatch_and_validate: Callable[[str], bytes],
) -> bytes:
    """Internal sequence for isolated fault tests; ordinary operator owns all callbacks.

    All failures after reserve retain debit. Completed means validated output, not refund.
    Mutable files are read into immutable values by validate under the campaign lock.
    """
    with campaign.locked():
        result, debit, identity = validate()
        if not result.ready:
            raise AdmissionError("preflight_rejected")
        campaign.reserve(debit, identity)
        key = None
        try:
            key = credential()
            campaign.transition("dispatched")
            output = dispatch_and_validate(key)
            campaign.transition("completed")
            return output
        finally:
            key = None


def execute(campaign: Campaign, inputs: Inputs) -> None:
    # The public path owns admission and exposes no transport/pricing/test overrides.
    if not preflight(campaign, inputs).ready:
        raise AdmissionError("preflight_rejected")

    def validate() -> tuple[Preflight, Debit, str]:
        result = snapshot(campaign, inputs)
        if not result.ready or result.reservation_micro_usd is None:
            raise AdmissionError("preflight_rejected")
        request = generated_input(inputs)
        debit = Debit(
            1, int(request.duration * 1_000_000), len(request.media), result.reservation_micro_usd
        )
        return result, debit, result.source_sha256

    def unavailable_credential() -> str:
        raise AdmissionError("live_phase_P1F_required")

    def unavailable_transport(key: str) -> bytes:
        raise AdmissionError("transport_redirect_boundary_unqualified")

    _admit(campaign, validate, unavailable_credential, unavailable_transport)
