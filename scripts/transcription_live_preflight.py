"""Zero-request Slice 3B preflight with sanitized evidence and mandatory cleanup on block."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from pydantic import ValidationError

from packages.config import Settings
from packages.media import MediaBoundaryError, MediaInspector
from packages.transcription.live import (
    APPROVED_ASSET_IDS,
    MAX_TOTAL_AUDIO_SECONDS,
    MAX_TOTAL_BYTES,
    PREFLIGHT_TTL_SECONDS,
    assert_safe_slice_root,
    asset_fingerprint,
    live_gate_failures,
    safe_endpoint_class,
)

SLICE_ROOT = Path("/tmp/colacci-law-slice3b")  # nosec B108
ASSET_ROOT = SLICE_ROOT / "generated"
REPORT_ROOT = SLICE_ROOT / "reports"
MANIFEST_PATH = SLICE_ROOT / "generated-manifest.json"
REPORT_PATH = REPORT_ROOT / "slice3b-live-preflight.json"


def _artifact_id(asset_id: str) -> str:
    return hashlib.sha256(f"slice3b:{asset_id}".encode()).hexdigest()[:32]


def _cleanup_blocked() -> None:
    shutil.rmtree(ASSET_ROOT, ignore_errors=True)
    shutil.rmtree(SLICE_ROOT / "objects", ignore_errors=True)
    MANIFEST_PATH.unlink(missing_ok=True)
    (REPORT_ROOT / "generated-audio-report.json").unlink(missing_ok=True)


def _write_report(report: dict[str, object]) -> None:
    REPORT_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(REPORT_PATH, 0o600)


def main() -> None:
    assert_safe_slice_root(SLICE_ROOT)
    failures = list(live_gate_failures(os.environ))
    safe_assets: list[dict[str, object]] = []
    settings_validated = False
    media_ready = False

    try:
        manifest = cast(dict[str, Any], json.loads(MANIFEST_PATH.read_text(encoding="utf-8")))
        assets = {
            str(item["asset_id"]): item for item in cast(list[dict[str, Any]], manifest["assets"])
        }
        if set(APPROVED_ASSET_IDS) - set(assets):
            failures.append("approved_generated_assets")
        else:
            inspector = MediaInspector(
                max_bytes=MAX_TOTAL_BYTES,
                max_duration_seconds=60,
                allowed_root=ASSET_ROOT,
            )
            for asset_id in APPROVED_ASSET_IDS:
                item = assets[asset_id]
                if item.get("synthetic") is not True:
                    failures.append("synthetic_media_attestation")
                    continue
                inspection = inspector.inspect(
                    ASSET_ROOT / str(item["filename"]), artifact_id=_artifact_id(asset_id)
                )
                safe_assets.append(
                    {
                        "asset_id": asset_id,
                        "synthetic": True,
                        "kind": str(item["kind"]),
                        "duration_seconds": round(inspection.duration_seconds, 3),
                        "byte_size": inspection.byte_size,
                        "channel_count": inspection.channel_count,
                        "language": "es" if asset_id == "spanish-short" else "en",
                        "hash_reference": inspection.hash_reference,
                        "chunking_strategy": "auto" if inspection.duration_seconds > 30 else "none",
                    }
                )
            long_item = assets["english-long"]
            long_safe = next(
                (item for item in safe_assets if item["asset_id"] == "english-long"), None
            )
            if (
                long_item.get("speaker_source_count") != 2
                or long_item.get("kind") != "english_multi_speaker_over_30_seconds"
                or long_safe is None
                or cast(float, long_safe["duration_seconds"]) <= 30
            ):
                failures.append("english_multi_speaker_over_30_seconds")
            if sum(cast(float, item["duration_seconds"]) for item in safe_assets) > (
                MAX_TOTAL_AUDIO_SECONDS
            ):
                failures.append("primary_audio_duration_cap")
            if sum(cast(int, item["byte_size"]) for item in safe_assets) > MAX_TOTAL_BYTES:
                failures.append("primary_upload_byte_cap")
            media_ready = len(safe_assets) == 3 and not any(
                item in failures
                for item in (
                    "approved_generated_assets",
                    "synthetic_media_attestation",
                    "english_multi_speaker_over_30_seconds",
                    "primary_audio_duration_cap",
                    "primary_upload_byte_cap",
                )
            )
    except (FileNotFoundError, KeyError, TypeError, ValueError, MediaBoundaryError):
        failures.append("generated_media_inspection")

    if not failures:
        try:
            Settings(_env_file=None)  # type: ignore[call-arg]
            settings_validated = True
        except ValidationError:
            failures.append("typed_settings_validation")

    now = datetime.now(UTC)
    failures = sorted(set(failures))
    report: dict[str, object] = {
        "version": "slice3b-live-preflight-v1",
        "status": "pass" if not failures else "blocked",
        "authorization_reference": "OWNER-CHAT-2026-08-17-SLICE-3B",
        "checked_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=PREFLIGHT_TTL_SECONDS)).isoformat(),
        "network_mode": "none",
        "provider_client_constructed": False,
        "provider_request_count": 0,
        "provider_retry_count": 0,
        "actual_cost_usd": "0.00",
        "gate_failures": failures,
        "credential_present": bool(os.environ.get("OPENAI_API_KEY", "").strip()),
        "project_configuration_present": bool(os.environ.get("OPENAI_PROJECT_ID", "").strip()),
        "account_data_controls_approved": (
            os.environ.get("OPENAI_PROJECT_DATA_CONTROLS_APPROVED") == "true"
        ),
        "endpoint": safe_endpoint_class(
            os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        ),
        "typed_settings_validated": settings_validated,
        "real_call_data_allowed": False,
        "analysis_enabled": False,
        "approved_media_ready": media_ready,
        "approved_assets": safe_assets,
        "asset_fingerprint": asset_fingerprint(safe_assets) if safe_assets else None,
        "approved_request_cap": 4,
        "approved_retry_cap": 1,
        "approved_total_audio_seconds": 120,
        "approved_total_bytes": 20 * 1024 * 1024,
        "approved_budget_usd": "1.00",
        "retained_media_count": 0 if failures else len(safe_assets),
        "cleanup_confirmed": bool(failures),
        "slice_root_class": "restricted_temporary",
    }
    if failures:
        _cleanup_blocked()
    _write_report(report)
    if failures:
        print(
            "transcription-live-preflight blocked: provider_requests=0 retries=0 "
            "actual_cost_usd=0.00 cleanup=confirmed"
        )
        raise SystemExit(2)
    print("transcription-live-preflight pass: provider_requests=0 ready_cases=3")


if __name__ == "__main__":
    main()
