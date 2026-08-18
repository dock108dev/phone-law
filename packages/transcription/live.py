"""Fail-closed controls shared by the Slice 3B preflight and live runner."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

from packages.contracts.media import MediaInspectionResult, TranscriptionUsageMetadata

AUTHORIZATION_REFERENCE = "OWNER-CHAT-2026-08-17-SLICE-3B"
APPROVED_ASSET_IDS = ("english-short", "spanish-short", "english-long")
APPROVED_MODEL = "gpt-4o-transcribe-diarize"
MAX_REQUESTS = 4
MAX_TOTAL_AUDIO_SECONDS = 120.0
MAX_TOTAL_BYTES = 20 * 1024 * 1024
MAX_BUDGET_USD = Decimal("1.00")
PREFLIGHT_TTL_SECONDS = 15 * 60

EXPECTED_ENVIRONMENT = {
    "APP_PROFILE": "live_test",
    "ALLOW_REAL_CALL_DATA": "false",
    "REAL_CALL_PROCESSING_AUTHORIZED": "false",
    "LIVE_TRANSCRIPTION_ENABLED": "true",
    "LIVE_TRANSCRIPTION_AUTHORIZED": "true",
    "TRANSCRIPTION_APPROVAL_REFERENCE": AUTHORIZATION_REFERENCE,
    "TRANSCRIPTION_MODEL_ID": APPROVED_MODEL,
    "TRANSCRIPTION_MAX_REQUESTS": "4",
    "TRANSCRIPTION_MAX_TOTAL_AUDIO_SECONDS": "120",
    "TRANSCRIPTION_MAX_TOTAL_BYTES": str(MAX_TOTAL_BYTES),
    "TRANSCRIPTION_TEST_BUDGET_USD": "1.00",
    "CALL_SOURCE_ADAPTER": "generated_synthetic",
    "TRANSCRIBER_ADAPTER": "openai_live",
    "ANALYZER_ADAPTER": "disabled",
    "NOTIFICATION_ADAPTER": "noop",
    "OBJECT_STORAGE_BACKEND": "local_synthetic",
    "MEDIA_TEMP_ROOT": "/tmp/colacci-law-slice3b/objects",  # nosec B108
    "OPENAI_PROJECT_DATA_CONTROLS_APPROVED": "true",
}


class LiveRunLimitError(RuntimeError):
    """A request was stopped before dispatch because an owner cap would be exceeded."""


def live_gate_failures(environment: Mapping[str, str]) -> tuple[str, ...]:
    failures = [
        name.lower()
        for name, expected in EXPECTED_ENVIRONMENT.items()
        if environment.get(name) != expected
    ]
    for name in ("OPENAI_API_KEY", "OPENAI_PROJECT_ID"):
        if not environment.get(name, "").strip():
            failures.append(name.lower())
    if not safe_endpoint_class(environment.get("OPENAI_BASE_URL", "https://api.openai.com/v1")):
        failures.append("openai_base_url")
    return tuple(sorted(set(failures)))


def safe_endpoint_class(value: str) -> dict[str, str] | None:
    parsed = urlsplit(value)
    regions = {
        "api.openai.com": "global",
        "us.api.openai.com": "us",
        "eu.api.openai.com": "eu",
        "au.api.openai.com": "au",
        "ca.api.openai.com": "ca",
        "jp.api.openai.com": "jp",
        "in.api.openai.com": "in",
        "sg.api.openai.com": "sg",
        "kr.api.openai.com": "kr",
        "gb.api.openai.com": "gb",
        "ae.api.openai.com": "ae",
    }
    region = regions.get((parsed.hostname or "").lower())
    if (
        parsed.scheme != "https"
        or region is None
        or parsed.path.rstrip("/") != "/v1"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        return None
    return {"endpoint_class": "official_openai", "region": region}


def asset_fingerprint(items: list[dict[str, object]]) -> str:
    canonical = json.dumps(items, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()[:12]


def assert_safe_slice_root(root: Path) -> Path:
    resolved = root.resolve(strict=False)
    if not resolved.is_absolute() or not str(resolved).startswith(
        "/tmp/colacci-law-slice3b"  # nosec B108
    ):
        raise LiveRunLimitError("live_slice_root_outside_boundary")
    return resolved


@dataclass
class LiveRunBudget:
    """Conservatively reserve every upload before the SDK can dispatch it."""

    request_count: int = 0
    retry_count: int = 0
    total_audio_seconds: float = 0.0
    total_bytes: int = 0
    reserved_cost_usd: Decimal = Decimal("0.00")
    observed_token_cost_usd: Decimal = Decimal("0.00")
    observed_usage_available: bool = False
    seen_artifacts: set[str] = field(default_factory=set, repr=False)

    def __call__(self, inspection: MediaInspectionResult) -> None:
        next_request = self.request_count + 1
        next_retry = self.retry_count + int(inspection.artifact_id in self.seen_artifacts)
        next_seconds = self.total_audio_seconds + inspection.duration_seconds
        next_bytes = self.total_bytes + inspection.byte_size
        next_reserved = self.reserved_cost_usd + Decimal("0.25")
        if next_request > MAX_REQUESTS:
            raise LiveRunLimitError("request_cap_exceeded")
        if next_retry > 1:
            raise LiveRunLimitError("retry_cap_exceeded")
        if next_seconds > MAX_TOTAL_AUDIO_SECONDS:
            raise LiveRunLimitError("audio_duration_cap_exceeded")
        if next_bytes > MAX_TOTAL_BYTES:
            raise LiveRunLimitError("upload_byte_cap_exceeded")
        if next_reserved > MAX_BUDGET_USD:
            raise LiveRunLimitError("application_budget_cap_exceeded")
        self.request_count = next_request
        self.retry_count = next_retry
        self.total_audio_seconds = next_seconds
        self.total_bytes = next_bytes
        self.reserved_cost_usd = next_reserved
        self.seen_artifacts.add(inspection.artifact_id)

    def record_usage(self, usage: TranscriptionUsageMetadata | None) -> None:
        if usage is None or (usage.input_tokens is None and usage.output_tokens is None):
            return
        input_tokens = Decimal(usage.input_tokens or 0)
        output_tokens = Decimal(usage.output_tokens or 0)
        incremental = (input_tokens * Decimal("2.50") + output_tokens * Decimal("10.00")) / Decimal(
            1_000_000
        )
        self.observed_usage_available = True
        self.observed_token_cost_usd += incremental
        if self.observed_token_cost_usd > MAX_BUDGET_USD:
            raise LiveRunLimitError("observed_cost_cap_exceeded")

    def safe_report(self) -> dict[str, int | float | str]:
        return {
            "request_count": self.request_count,
            "retry_count": self.retry_count,
            "total_audio_seconds": round(self.total_audio_seconds, 3),
            "total_bytes": self.total_bytes,
            "reserved_cost_usd": str(self.reserved_cost_usd),
            "observed_token_cost_usd": (
                str(self.observed_token_cost_usd)
                if self.observed_usage_available
                else "unavailable"
            ),
        }
