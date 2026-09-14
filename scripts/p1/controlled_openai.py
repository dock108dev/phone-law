"""Standalone P1 boundary. No application configuration, SDK, or arbitrary audio input."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import http.client
import io
import json
import math
import os
import re
import select
import shutil
import ssl
import stat
import subprocess  # nosec B404
import tempfile
import time
import unicodedata
import wave
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO

MODEL = "whisper-1"
CAMPAIGN = "colacci-law-p1-20260913"
MAX_REQUESTS = 6
MAX_RETRIES = 0
MAX_SECONDS = 90
MAX_TOTAL_SECONDS = 540
MAX_BYTES = 4 * 1024 * 1024
MAX_TOTAL_BYTES = 24 * 1024 * 1024
MAX_SPEND_MICRO_USD = 2_000_000
PRICE_PER_MINUTE_MICRO_USD = 6000
MAX_RESPONSE_BYTES = 256 * 1024
TIMEOUT_SECONDS = 45
CASES = (
    (
        "english",
        "en",
        "This generated test describes a blue garden and a yellow bicycle. "
        "No real person or client is represented.",
    ),
    (
        "spanish",
        "es",
        "Esta prueba generada describe un jardín azul y una bicicleta amarilla. "
        "No representa a una persona real ni a un cliente.",
    ),
    ("long", "en", "This generated test describes a blue garden and a yellow bicycle. " * 8),
)


class BlockedError(Exception):
    """Only fixed diagnostic codes may cross this boundary."""


@dataclass(frozen=True)
class Audio:
    case: str
    language: str
    content: bytes = field(repr=False)
    seconds: float


def inspect_audio(case: str, language: str, content: bytes) -> Audio:
    if (case, language) not in {(c, lang) for c, lang, _ in CASES}:
        raise BlockedError("case_not_allowlisted")
    if not 44 < len(content) <= MAX_BYTES:
        raise BlockedError("audio_byte_limit")
    try:
        with wave.open(io.BytesIO(content), "rb") as audio:
            frames = audio.getnframes()
            if (
                audio.getnchannels(),
                audio.getsampwidth(),
                audio.getframerate(),
                audio.getcomptype(),
            ) != (1, 2, 16000, "NONE"):
                raise BlockedError("audio_format")
            if len(audio.readframes(frames)) != frames * 2:
                raise BlockedError("audio_truncated")
            seconds = frames / 16000
    except wave.Error, EOFError:
        raise BlockedError("audio_format") from None
    if not 0 < seconds <= MAX_SECONDS or (case == "long" and seconds <= 30):
        raise BlockedError("audio_duration_limit")
    return Audio(case, language, content, seconds)


def reservation(audio: Audio) -> int:
    # Whole minutes rounded UP: conservative vs duration billing, including ambiguous failures.
    return math.ceil(audio.seconds / 60) * PRICE_PER_MINUTE_MICRO_USD


def private_file(path: Path) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise BlockedError("private_file_permissions")
        data = stream.read(65537)
        if len(data) > 65536:
            raise BlockedError("private_file_size")
        return data


def write_record(path: Path, value: Any) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def source_identity() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def preflight(approval: dict[str, Any], key_available: bool, now: float) -> list[str]:
    """Pure local function: never reads a credential or constructs a client."""
    missing = []
    required = {
        "campaign": CAMPAIGN,
        "model": MODEL,
        "source_sha256": source_identity(),
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
    }
    for name, expected in required.items():
        actual = approval.get(name)
        if type(actual) is not type(expected) or actual != expected:
            missing.append(name)
    for name, pattern in (
        ("project_id", r"proj_[A-Za-z0-9_-]{4,128}"),
        ("organization_id", r"org-[A-Za-z0-9_-]{4,128}"),
    ):
        if not isinstance(approval.get(name), str) or not re.fullmatch(pattern, approval[name]):
            missing.append(name)
    # These are owner-supplied local references, not claims that an API has proved ownership.
    for name in (
        "ownership_evidence_reference",
        "terms_evidence_reference",
        "data_controls_evidence_reference",
    ):
        if not isinstance(approval.get(name), str) or not approval[name].strip():
            missing.append(name)
    expires = approval.get("expires_at")
    if (
        not isinstance(expires, (int, float))
        or isinstance(expires, bool)
        or not now < expires <= now + 86400
    ):
        missing.append("fresh_approval_expiry")
    if not key_available:
        missing.append("ephemeral_key_descriptor")
    return missing


def key_descriptor_available(fd: int | None) -> bool:
    """Inspect descriptor metadata only; a preflight must never consume key bytes."""
    try:
        return fd is not None and fd >= 3 and stat.S_ISFIFO(os.fstat(fd).st_mode)
    except OSError:
        return False


def close_descriptor(fd: int | None) -> None:
    if fd is not None and fd >= 3:
        with contextlib.suppress(OSError):
            os.close(fd)


def read_key(fd: int) -> str:
    # Pipe only: no files, environment keys, terminal input, argv secrets or keychain search.
    try:
        if fd < 3 or not stat.S_ISFIFO(os.fstat(fd).st_mode):
            raise BlockedError("credential_requires_pipe")
        data = bytearray()
        deadline = time.monotonic() + 5
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([fd], [], [], remaining)[0]:
                raise BlockedError("credential_pipe_timeout")
            chunk = os.read(fd, 4097 - len(data))
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > 4096:
                raise BlockedError("credential_size")
        key = data.decode("ascii").strip()
        if not key.startswith("sk-proj-") or not re.fullmatch(r"[A-Za-z0-9_-]{20,4096}", key):
            raise BlockedError("credential_format")
        return key
    except OSError, UnicodeError, ValueError:
        raise BlockedError("credential_unavailable") from None
    finally:
        close_descriptor(fd)


class Ledger:
    """Campaign-wide lock and fsynced reservations survive crashes and new attempt directories."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = path.parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise BlockedError("ledger_directory_permissions")
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        self.stream: BinaryIO = os.fdopen(fd, "r+b")
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise BlockedError("ledger_permissions")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            raw = self.stream.read(65537)
            if len(raw) > 65536:
                raise BlockedError("ledger_invalid")
            self.events: list[dict[str, Any]] = [json.loads(line) for line in raw.splitlines()]
            self._validate()
        except BaseException:
            self.stream.close()
            raise

    def _validate(self) -> None:
        for index, event in enumerate(self.events):
            expected = "reserved" if index % 2 == 0 else "passed"
            if event.get("state") != expected or event.get("attempt") != index // 2 + 1:
                raise BlockedError("ledger_failed_or_invalid")
            if expected == "reserved":
                if set(event) != {"state", "attempt", "seconds", "bytes", "micro_usd"}:
                    raise BlockedError("ledger_invalid")
                seconds, size, cost = event["seconds"], event["bytes"], event["micro_usd"]
                if (
                    type(seconds) not in (int, float)
                    or not 0 < seconds <= MAX_SECONDS
                    or type(size) is not int
                    or not 44 < size <= MAX_BYTES
                    or type(cost) is not int
                    or cost != math.ceil(seconds / 60) * PRICE_PER_MINUTE_MICRO_USD
                ):
                    raise BlockedError("ledger_invalid")
        if len(self.events) % 2:
            raise BlockedError("ledger_unresolved_request")

    def _append(self, event: dict[str, Any]) -> None:
        self.stream.seek(0, os.SEEK_END)
        self.stream.write((json.dumps(event, allow_nan=False) + "\n").encode())
        self.stream.flush()
        os.fsync(self.stream.fileno())
        self.events.append(event)

    def reserve(self, audio: Audio) -> int:
        self._validate()
        audio = inspect_audio(audio.case, audio.language, audio.content)
        rows = self.events[::2]
        if len(rows) >= MAX_REQUESTS:
            raise BlockedError("request_limit")
        if sum(row["seconds"] for row in rows) + audio.seconds > MAX_TOTAL_SECONDS:
            raise BlockedError("total_duration_limit")
        if sum(row["bytes"] for row in rows) + len(audio.content) > MAX_TOTAL_BYTES:
            raise BlockedError("total_byte_limit")
        if sum(row["micro_usd"] for row in rows) + reservation(audio) > MAX_SPEND_MICRO_USD:
            raise BlockedError("spending_limit")
        number = len(rows) + 1
        self._append(
            {
                "state": "reserved",
                "attempt": number,
                "seconds": audio.seconds,
                "bytes": len(audio.content),
                "micro_usd": reservation(audio),
            }
        )
        return number

    def passed(self, attempt: int) -> None:
        self._append({"state": "passed", "attempt": attempt})

    def close(self) -> None:
        self.stream.close()


def multipart(audio: Audio) -> tuple[bytes, str]:
    boundary = "colacci-p1-" + os.urandom(16).hex()
    body = bytearray()
    for name, value in (
        ("model", MODEL),
        ("response_format", "verbose_json"),
        ("language", audio.language),
        ("temperature", "0"),
        ("timestamp_granularities[]", "segment"),
    ):
        body.extend(
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
            ).encode()
        )
    body.extend(
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
            'filename="generated.wav"\r\nContent-Type: audio/wav\r\n\r\n'
        ).encode()
    )
    body.extend(audio.content)
    body.extend(f"\r\n--{boundary}--\r\n".encode())
    if len(body) > MAX_BYTES + 4096:
        raise BlockedError("request_byte_limit")
    return bytes(body), boundary


def send(audio: Audio, key: str, approval: dict[str, Any]) -> tuple[int, bytes]:
    body, boundary = multipart(audio)
    # Fixed TLS origin, no environment proxies, redirects, SDK retries or alternate endpoints.
    connection = http.client.HTTPSConnection(
        "api.openai.com", timeout=TIMEOUT_SECONDS, context=ssl.create_default_context()
    )
    try:
        connection.request(
            "POST",
            "/v1/audio/transcriptions",
            body,
            {
                "Authorization": "Bearer " + key,
                "OpenAI-Project": approval["project_id"],
                "OpenAI-Organization": approval["organization_id"],
                "Content-Type": "multipart/form-data; boundary=" + boundary,
            },
        )
        response = connection.getresponse()
        content = response.read(MAX_RESPONSE_BYTES + 1)
        if len(content) > MAX_RESPONSE_BYTES:
            raise BlockedError("response_byte_limit")
        return response.status, content
    finally:
        connection.close()


def validate_response(audio: Audio, content: bytes) -> dict[str, Any]:
    if len(content) > MAX_RESPONSE_BYTES:
        raise BlockedError("response_byte_limit")
    try:
        result = json.loads(content)
        text = result["text"]
        duration = result["duration"]
        segments = result["segments"]
        language = result["language"].lower()
        if (
            not isinstance(text, str)
            or not text.strip()
            or type(duration) not in (int, float)
            or not math.isfinite(duration)
            or abs(duration - audio.seconds) > 2
            or language not in ({"en", "english"} if audio.language == "en" else {"es", "spanish"})
            or not isinstance(segments, list)
            or not 0 < len(segments) <= 500
        ):
            raise BlockedError("response_contract")
        last_start = 0.0
        for segment in segments:
            start, end = segment["start"], segment["end"]
            if (
                type(start) not in (int, float)
                or type(end) not in (int, float)
                or not last_start <= start < end <= audio.seconds + 2
                or not isinstance(segment["text"], str)
                or not segment["text"].strip()
            ):
                raise BlockedError("response_timestamps")
            last_start = start
        normalized = "".join(
            c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c)
        )
        words = {"garden", "bicycle"} if audio.language == "en" else {"jardin", "bicicleta"}
        if not words.issubset(set(re.findall(r"\w+", normalized))):
            raise BlockedError("response_content_check")
        return {
            "case": audio.case,
            "language_matches": True,
            "content_check": True,
            "segments": len(segments),
            "timestamps_valid": True,
            "provider_duration_seconds": duration,
            "billed_cost_usd": None,
        }
    except ValueError, TypeError, KeyError, AttributeError:
        raise BlockedError("response_contract") from None


def transcribe(
    audio: Audio, ledger: Ledger, transport: Callable[[Audio], tuple[int, bytes]]
) -> dict[str, Any]:
    number = ledger.reserve(audio)  # durable debit BEFORE client construction or network
    try:
        status, content = transport(audio)
        if status != 200:
            raise BlockedError("provider_http_failure")
        result = validate_response(audio, content)
    except BlockedError:
        raise
    except Exception:
        raise BlockedError("provider_transport_failure") from None
    ledger.passed(number)
    return {**result, "attempt": number, "reserved_micro_usd": reservation(audio)}


def generate(root: Path) -> list[Audio]:
    # Only source-authored text, built-in local voices; never a caller-selected media path.
    env = {"PATH": "/usr/bin:/bin", "HOME": str(root), "TMPDIR": str(root)}

    def run(args: list[str]) -> bytes:
        return subprocess.run(args, check=True, capture_output=True, timeout=120, env=env).stdout  # noqa: S603  # nosec B603

    voices: dict[str, str] = {}
    for line in run(["/usr/bin/say", "-v", "?"]).decode().splitlines():
        match = re.match(r"(.+?)\s+(en_\w+|es_\w+)\s", line)
        if match:
            voices.setdefault(match[2][:2], match[1].strip())
    if set(voices) != {"en", "es"}:
        raise BlockedError("local_voices_missing")
    assets = []
    for case, language, text in CASES:
        aiff, wav = root / f"{case}.aiff", root / f"{case}.wav"
        run(["/usr/bin/say", "-v", voices[language], "-r", "140", "-o", str(aiff), text])
        run(
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
            ]
        )
        assets.append(inspect_audio(case, language, wav.read_bytes()))
    return assets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("preflight", "generate-check", "live"))
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--key-fd", type=int)
    args = parser.parse_args()
    os.umask(0o077)
    args.evidence.mkdir(mode=0o700, parents=False, exist_ok=False)
    outcome: dict[str, Any] = {
        "mode": args.mode,
        "source_sha256": source_identity(),
        "provider_requests": 0,
        "reserved_micro_usd": 0,
        "automatic_retries": MAX_RETRIES,
        "billed_cost_usd": None,
    }
    runtime: Path | None = None
    ledger: Ledger | None = None
    key: str | None = None
    try:
        if args.mode != "generate-check":
            approval = json.loads(private_file(args.approval)) if args.approval else {}
            missing = preflight(approval, key_descriptor_available(args.key_fd), time.time())
            write_record(
                args.evidence / "preflight.json",
                {"missing": missing, "provider_requests": 0, "client_constructions": 0},
            )
            if missing:
                raise BlockedError("provider_prerequisites_missing")
            if args.mode == "preflight":
                outcome["result"] = "preflight_passed_no_client_constructed"
                return 0
        runtime = Path(tempfile.mkdtemp(prefix="colacci-p1-generated-"))
        assets = generate(runtime)
        write_record(
            args.evidence / "generated.json",
            [
                {
                    "case": a.case,
                    "seconds": a.seconds,
                    "bytes": len(a.content),
                    "generated_only": True,
                    "sha256": hashlib.sha256(a.content).hexdigest(),
                }
                for a in assets
            ],
        )
        if args.mode == "generate-check":
            outcome["result"] = "generated_audio_verified_offline"
            return 0
        # Validate again after generation, including the short-lived approval's expiry.
        if preflight(approval, key_descriptor_available(args.key_fd), time.time()):
            raise BlockedError("approval_expired")
        key_fd = args.key_fd
        args.key_fd = None
        key = read_key(key_fd)
        ledger = Ledger(Path.home() / ".local/state/colacci-law" / (CAMPAIGN + ".jsonl"))
        for audio in assets:
            if preflight(approval, True, time.time()):
                raise BlockedError("approval_expired")

            def transport(a: Audio) -> tuple[int, bytes]:
                outcome["provider_requests"] += 1
                outcome["reserved_micro_usd"] += reservation(a)
                if key is None:
                    raise BlockedError("credential_unavailable")
                return send(a, key, approval)

            result = transcribe(audio, ledger, transport)
            write_record(args.evidence / (audio.case + ".json"), result)
        outcome["result"] = "live_generated_contract_passed"
        return 0
    except BlockedError as exc:
        outcome["result"] = str(exc)
        return 2
    except Exception:
        outcome["result"] = "local_failure_sanitized"
        return 2
    finally:
        key = None
        close_descriptor(args.key_fd)
        if ledger:
            ledger.close()
        if runtime:
            try:
                shutil.rmtree(runtime)
            except OSError:
                outcome["result"] = "cleanup_failed"
        outcome["generated_media_removed"] = runtime is None or not runtime.exists()
        outcome["credential_descriptor_closed"] = True
        write_record(args.evidence / "outcome.json", outcome)
        print(json.dumps(outcome, sort_keys=True))
        if not outcome["generated_media_removed"]:
            raise SystemExit(2)


if __name__ == "__main__":
    raise SystemExit(main())
