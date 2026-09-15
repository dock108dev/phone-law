"""Explicit single supervised synthetic probe; ordinary application remains offline."""

from __future__ import annotations

import argparse
import getpass
import io
import json
import math
import os
import re
import subprocess  # nosec B404 - fixed local speech generator
import sys
import tempfile
import time
import wave
from pathlib import Path
from typing import Any

from packages.review.transcript_import import load_transcript_only_artifact

from .admission import ROOT, implementation_identity
from .campaign import (
    CAMPAIGN,
    AdmissionError,
    Campaign,
    Debit,
    create_private,
    decode,
    digest,
    encoded,
    private_directory,
    read_private,
)
from .cli_adapter import MODEL, AdapterError, Request, convert
from .cli_check import load_contract
from .cli_process import _execute, verified_executable
from .controlled_openai import BlockedError, read_key
from .probe_transport import fixed_tunnel

SCOPE = "single-supervised-local-probe-20260913"
DIRECTORY = Path("/tmp/colacci-law-local-probe-20260913").resolve()  # noqa: S108 - checked 0700 owner directory
TEXT = (
    "This is an invented local development test. The blue bicycle is beside the garden. "
    "Tomorrow we will count yellow flowers and write a short note."
)
VOICE = "Albert"
RATE = 140
ESTIMATE_MICRO_USD = 60_000  # Planning assumption, NEVER an enforceable billing ceiling.


def prepare() -> dict[str, Any]:
    DIRECTORY.mkdir(mode=0o700, exist_ok=True)
    private_directory(DIRECTORY)
    if (DIRECTORY / "sample.json").exists():
        _request, receipt = sample()
        return receipt
    with tempfile.TemporaryDirectory(prefix="speech-", dir=DIRECTORY) as temporary:
        root = Path(temporary)
        env = {"HOME": str(root), "TMPDIR": str(root), "PATH": "/usr/bin:/bin"}
        aiff, wav = root / "speech.aiff", root / "speech.wav"
        prefix = ["/usr/bin/sandbox-exec", "-p", "(version 1)(allow default)(deny network*)"]
        for args in (
            ["/usr/bin/say", "-v", VOICE, "-r", str(RATE), "-o", str(aiff), TEXT],
            [
                "/usr/bin/afconvert",
                "-f",
                "WAVE",
                "-d",
                "LEI16@16000",
                "-c",
                "1",
                str(aiff),
                str(wav),
            ],
        ):
            subprocess.run(prefix + args, env=env, capture_output=True, check=True, timeout=30)  # noqa: S603  # nosec B603
        with wave.open(str(wav), "rb") as audio:
            frames = audio.readframes(audio.getnframes())
            if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (1, 2, 16000):
                raise AdmissionError("generation_format")
        canonical = io.BytesIO()
        with wave.open(canonical, "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(16000)
            audio.writeframes(frames)
        raw = canonical.getvalue()
        duration = len(frames) / 32000
        if not 10 <= duration <= 15:
            raise AdmissionError("generation_duration")
        receipt = {
            "scope": SCOPE,
            "text": TEXT,
            "voice": VOICE,
            "rate": RATE,
            "generator": "macOS-say-afconvert-local-v1",
            "language": "en",
            "format": "mono-PCM16-16000Hz",
            "duration": duration,
            "bytes": len(raw),
            "sha256": digest(raw),
            "generator_hashes": {
                p: digest(Path(p).read_bytes()) for p in ("/usr/bin/say", "/usr/bin/afconvert")
            },
            "estimate_micro_usd": ESTIMATE_MICRO_USD,
            "hard_billing_ceiling": False,
        }
        create_private(DIRECTORY / "generated.wav", raw)
        create_private(DIRECTORY / "sample.json", encoded(receipt))
        return receipt


def sample() -> tuple[Request, dict[str, Any]]:
    receipt = decode(read_private(DIRECTORY / "sample.json"))
    raw = read_private(DIRECTORY / "generated.wav", 4 * 1024 * 1024)
    with wave.open(io.BytesIO(raw), "rb") as audio:
        duration = audio.getnframes() / 16000
        if (
            audio.getnchannels(),
            audio.getsampwidth(),
            audio.getframerate(),
            audio.getcomptype(),
        ) != (1, 2, 16000, "NONE"):
            raise AdmissionError("sample_format")
    for key, expected in {
        "scope": SCOPE,
        "text": TEXT,
        "voice": VOICE,
        "rate": RATE,
        "language": "en",
        "sha256": digest(raw),
        "bytes": len(raw),
        "duration": duration,
    }.items():
        if receipt.get(key) != expected:
            raise AdmissionError("sample_changed")
    if not 10 <= duration <= 15:
        raise AdmissionError("sample_duration")
    return Request(raw, duration, "en"), receipt


def approval_record(path: Path, request: Request) -> dict[str, Any]:
    record = decode(read_private(path))
    for key, expected in {
        "scope": SCOPE,
        "campaign": CAMPAIGN,
        "model": MODEL,
        "source_sha256": implementation_identity(),
        "media_sha256": digest(request.media),
        "contract_sha256": digest((ROOT / "scripts/p1/cli-contract.json").read_bytes()),
        "requests": 1,
        "automatic_retries": 0,
        "estimate_micro_usd": ESTIMATE_MICRO_USD,
        "authorize_estimated_request_without_guaranteed_2usd_ceiling": True,
        "accept_same_origin_redirect_gets": True,
        "accept_unverified_physical_request_count": True,
        "project_key_matches_selected_project": True,
        "example": False,
    }.items():
        if type(record.get(key)) is not type(expected) or record[key] != expected:
            raise AdmissionError("probe_approval_required")
    if (
        record.get("account_kind") not in ("personal_development", "firm")
        or not isinstance(record.get("project_id"), str)
        or not re.fullmatch(r"proj_[A-Za-z0-9_-]+", record["project_id"])
        or not record.get("reviewer")
        or type(record.get("expires_at")) is not int
        or not time.time() < record["expires_at"] <= time.time() + 86400
    ):
        raise AdmissionError("probe_account_or_expiry")
    # Retain the actual owner's non-secret decisions as evidence, not manufactured flags.
    ref = record["owner_decision"]
    if digest(read_private(Path(ref["path"]))) != ref["sha256"]:
        raise AdmissionError("owner_decision_changed")
    return record


def validate(campaign: Campaign, approval: Path) -> tuple[Request, dict[str, Any], Debit]:
    request, _ = sample()
    record = approval_record(approval, request)
    total, pending, _ = campaign.state()
    if pending:
        raise AdmissionError("unresolved_debit")
    if (campaign.root / (SCOPE + ".used")).exists():
        raise AdmissionError("single_probe_already_attempted")
    debit = Debit(
        1, math.ceil(request.duration * 1_000_000), len(request.media), ESTIMATE_MICRO_USD
    )
    total.plus(debit)
    contract = load_contract()
    binary = Path.home() / contract["relative_install_path"]
    if digest(binary.read_bytes()) != contract["binary_sha256"]:
        raise AdmissionError("tool_changed")
    return request, record, debit


def terminal_credential() -> str:
    # Owner supplies selected project's key locally; never scrape saved Codex/account auth.
    key = getpass.getpass("Selected Platform project's API key (hidden, never saved): ")
    if len(key) > 4096:
        raise AdmissionError("credential_size")
    data = key.encode("ascii")
    read_fd, write_fd = os.pipe()
    try:
        os.write(write_fd, data)
    finally:
        os.close(write_fd)
        key = ""
        data = b""
    return read_key(read_fd)


def run(approval: Path) -> dict[str, Any]:
    if not sys.stdin.isatty():
        raise AdmissionError("owner_local_terminal_required")
    campaign = Campaign(Path.home() / ".local/state/colacci-law")
    # P1A help probes contain no credential or provider operation.
    executable = verified_executable()
    outcome: dict[str, Any] = {
        "scope": SCOPE,
        "status": "not_dispatched",
        "provider_dispatch_attempts": 0,
        "estimated_micro_usd": ESTIMATE_MICRO_USD,
        "provider_reported_usage": None,
        "verified_billed_micro_usd": None,
        "hard_billing_ceiling": False,
        "physical_http_request_count": None,
    }
    reserved = False
    try:
        with campaign.locked():
            request, record, debit = validate(campaign, approval)
            outcome.update(
                source_sha256=record["source_sha256"],
                project_id=record["project_id"],
                media_sha256=digest(request.media),
            )
            campaign.reserve(debit, record["source_sha256"])
            reserved = True
            create_private(
                campaign.root / (SCOPE + ".used"),
                encoded({"approval_sha256": digest(read_private(approval))}),
            )
            outcome["local_reservation_micro_usd"] = debit.micro_usd
            key = None
            try:
                key = terminal_credential()
                campaign.transition("dispatched")
                outcome["provider_dispatch_attempts"] = 1
                with fixed_tunnel() as tunnel:
                    payload = _execute(
                        executable,
                        request,
                        key,
                        endpoint="https://api.openai.com/v1",
                        _probe_port=tunnel.server_address[1],
                        _project=record["project_id"],
                    )
                base = load_transcript_only_artifact(
                    ROOT / "fixtures/transcript-only/invented-call.json"
                )
                transcript = convert(
                    payload, request, base.transcript.provenance, "single-local-probe"
                )
                # Converter's mocked provenance is never published as live evidence.
                outcome.update(
                    status="observed_local_cli_success",
                    usable_text=True,
                    segments=len(transcript.segments),
                    speaker_labels=len(
                        {s.identity.raw_provider_speaker_label for s in transcript.segments}
                    ),
                    text=transcript.original_language_text,
                    timestamps=[
                        {"start": s.start_seconds, "end": s.end_seconds}
                        for s in transcript.segments
                    ],
                )
                usage = json.loads(payload).get("usage")
                # Retain only numeric usage structure, never arbitrary provider strings.
                outcome["provider_reported_usage"] = numeric_usage(usage)
                # A valid transcript does not resolve unobserved redirect GET accounting.
                # Keep the campaign hold; no later request is admitted automatically.
                outcome["campaign_hold"] = "physical_request_count_and_billed_cost_unverified"
            finally:
                key = None
    except (
        AdapterError,
        AdmissionError,
        BlockedError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        EOFError,
        KeyboardInterrupt,
    ) as exc:
        outcome["status"] = "stopped_debit_retained" if reserved else "blocked_before_reservation"
        outcome["code"] = (
            exc.code
            if isinstance(exc, AdapterError)
            else (str(exc) if isinstance(exc, (AdmissionError, BlockedError)) else "local_failure")
        )
    finally:
        (DIRECTORY / "generated.wav").unlink(missing_ok=True)
        outcome["media_removed"] = not (DIRECTORY / "generated.wav").exists()
        create_private(DIRECTORY / f"outcome-{time.time_ns()}.json", encoded(outcome))
    return outcome


def numeric_usage(value: Any) -> Any:
    if type(value) in (int, float) and math.isfinite(value) and value >= 0:
        return value
    if type(value) is dict:
        return {
            k: numeric_usage(v)
            for k, v in value.items()
            if k
            in {
                "input_tokens",
                "output_tokens",
                "total_tokens",
                "input_token_details",
                "text_tokens",
                "audio_tokens",
                "seconds",
            }
        }
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "preflight", "run"))
    parser.add_argument("--approval", type=Path)
    args = parser.parse_args()
    try:
        if args.mode == "prepare":
            print(json.dumps(prepare(), sort_keys=True))
            return 0
        if args.approval is None:
            raise AdmissionError("probe_approval_required")
        if args.mode == "preflight":
            campaign = Campaign(Path.home() / ".local/state/colacci-law")
            with campaign.locked():
                validate(campaign, args.approval)
            print(json.dumps({"status": "offline_preflight_pass", "provider_requests": 0}))
            return 0
        outcome = run(args.approval)
        print(json.dumps(outcome, sort_keys=True))
        return 0 if outcome["status"] == "observed_local_cli_success" else 2
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        AdmissionError,
        subprocess.SubprocessError,
        wave.Error,
    ):
        print(
            json.dumps(
                {"status": "blocked", "provider_requests": 0, "code": "probe_prerequisite_unmet"}
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
