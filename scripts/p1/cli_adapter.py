"""Explicit offline operator adapter. Live process admission awaits P1C."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from packages.contracts.review import (
    DiarizationStatus,
    Provenance,
    Speaker,
    SpeakerIdentity,
    Transcript,
    TranscriptionTransportProvenance,
    TranscriptSegment,
    ValueState,
)

from .cli_check import load_contract

MODEL = "gpt-4o-transcribe-diarize"
MAX_OUTPUT = 256 * 1024


class AdapterError(Exception):
    """Only fixed diagnostic codes cross the operator boundary."""

    def __init__(self, code: str) -> None:
        allowed = {
            "selection_rejected",
            "p1c_required",
            "invalid_input",
            "invalid_output",
            "spawn_failed",
            "stdin_failed",
            "process_failed",
            "output_overflow",
            "timeout",
            "cancelled",
            "cleanup_failed",
            "tool_rejected",
        }
        self.code = code if code in allowed else "process_failed"
        super().__init__(self.code)


@dataclass(frozen=True)
class OperatorSelection:
    profile: str = "local_dev"
    transport: str = "openai_cli_local"

    def __post_init__(self) -> None:
        if (self.profile, self.transport) != ("local_dev", "openai_cli_local"):
            raise AdapterError("selection_rejected")


@dataclass(frozen=True, repr=False)
class Request:
    media: bytes
    duration: float
    language: Literal["en", "es"]

    def __post_init__(self) -> None:
        if (
            type(self.media) is not bytes
            or not 0 < len(self.media) <= 4 * 1024 * 1024
            or type(self.duration) not in (float, int)
            or not math.isfinite(self.duration)
            or not 0 < self.duration <= 90
            or self.language not in ("en", "es")
        ):
            raise AdapterError("invalid_input")

    @property
    def body(self) -> bytes:
        return json.dumps({"language": self.language}).encode()

    @property
    def arguments(self) -> tuple[str, ...]:
        # File and production endpoint are owned by the process boundary.
        return (
            "audio:transcriptions",
            "create",
            "--model",
            MODEL,
            "--response-format",
            "diarized_json",
            "--chunking-strategy",
            "auto",
            "--format",
            "json",
        )


class Runner(Protocol):
    def run(self, request: Request) -> bytes: ...


@dataclass(repr=False)
class MockRunner:
    output: bytes = field(repr=False)

    def run(self, request: Request) -> bytes:
        return self.output


class LiveRunner:
    def run(self, request: Request) -> bytes:
        # No credential access, executable checks or child starts before durable admission.
        raise AdapterError("p1c_required")


def _reject_constant(value: str) -> None:
    raise ValueError("nonfinite")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate")
        result[key] = value
    return result


def convert(payload: bytes, request: Request, provenance: Provenance, call_id: str) -> Transcript:
    """Strict invented CLI output to the existing contract; never claims live proof."""
    try:
        if type(payload) is not bytes or not 0 < len(payload) <= MAX_OUTPUT:
            raise ValueError
        data = json.loads(payload, object_pairs_hook=_pairs, parse_constant=_reject_constant)
        if type(data) is not dict or type(data.get("text")) is not str or not data["text"].strip():
            raise ValueError
        if type(data.get("segments")) is not list or not data["segments"]:
            raise ValueError
        if "language" in data and data["language"] not in (
            request.language,
            {"en": "english", "es": "spanish"}[request.language],
        ):
            raise ValueError
        if "duration" in data and (
            type(data["duration"]) not in (float, int)
            or not math.isfinite(data["duration"])
            or not 0 < data["duration"] <= request.duration
        ):
            raise ValueError
        labels: dict[str, str] = {}
        segments = []
        for index, item in enumerate(data["segments"]):
            if type(item) is not dict:
                raise ValueError
            label = item.get("speaker")
            if type(label) is not str or not label.strip() or len(label) > 128:
                raise ValueError
            stable = labels.setdefault(label, f"speaker-{len(labels) + 1:03d}")
            start, end = item["start"], item["end"]
            if any(type(t) not in (int, float) or not math.isfinite(t) for t in (start, end)):
                raise ValueError
            if not 0 <= start < end <= request.duration:
                raise ValueError
            segments.append(
                TranscriptSegment(
                    segment_id=f"segment-{index + 1:04d}",
                    speaker=Speaker.UNKNOWN_PARTICIPANT,
                    identity=SpeakerIdentity(
                        speaker=Speaker.UNKNOWN_PARTICIPANT,
                        verification_state=ValueState.UNKNOWN,
                        raw_provider_speaker_label=stable,
                    ),
                    start_seconds=float(start),
                    end_seconds=float(end),
                    text=item["text"],
                )
            )
        if data["text"].split() != " ".join(s.text for s in segments).split():
            raise ValueError
        lock = load_contract()
        fingerprint = "sha256:" + hashlib.sha256(request.media).hexdigest()[:12]
        safe = provenance.model_copy(
            update={
                "environment": "local_dev",
                "transcript_adapter": "openai-cli-local",
                "transcript_model_version": MODEL,
                "adapter_version": "p1b-v1",
                "endpoint_class": None,
                "project_configuration": None,
                "authorization_reference": None,
                "transcription_transport": TranscriptionTransportProvenance(
                    transport="openai_cli_local",
                    declared_contract_version=lock["contract"],
                    observed_cli_version="unavailable",
                    model_id=MODEL,
                    requested_response_format="diarized_json",
                    generated_asset_fingerprint=fingerprint,
                    attempt_number=1,
                    result_kind="mocked_cli",
                ),
            }
        )
        return Transcript(
            transcript_id=f"cli-{hashlib.sha256(payload).hexdigest()[:24]}",
            call_id=call_id,
            language=request.language,
            diarization_status=DiarizationStatus.AVAILABLE,
            original_language_text=data["text"],
            provider_response_version="diarized-json-p1b-v1",
            media_hash_reference=fingerprint,
            segments=tuple(segments),
            provenance=safe,
        )
    except ValueError, TypeError, KeyError, OverflowError, RecursionError:
        raise AdapterError("invalid_output") from None


def transcribe(
    selection: OperatorSelection,
    request: Request,
    provenance: Provenance,
    call_id: str,
    *,
    runner: Runner | None = None,
) -> Transcript:
    OperatorSelection(selection.profile, selection.transport)
    try:
        output = (runner or LiveRunner()).run(request)
    except AdapterError:
        raise
    except Exception:
        raise AdapterError("process_failed") from None
    return convert(output, request, provenance, call_id)
