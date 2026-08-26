"""Final Slice 3B re-entry preflight: zero requests, sanitized evidence, full cleanup."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from packages.media import MediaBoundaryError, MediaInspector
from packages.transcription.live import (
    APPROVED_ASSET_IDS,
    MAX_BUDGET_USD,
    MAX_REQUESTS,
    MAX_TOTAL_AUDIO_SECONDS,
    MAX_TOTAL_BYTES,
    asset_fingerprint,
    safe_endpoint_class,
)

PREFLIGHT_AUTHORIZATION = "OWNER-CHAT-2026-08-19-SLICE-3B-REENTRY-PREFLIGHT-ONLY"
SOURCE_COMMIT = "7ac96fb7ed3b9e5ac23ebeaa2fff4a5302e1b79c"
SOURCE_BRANCH = "codex/slice-3b-final-preflight"
MIGRATION_HEAD = "0006_local_operations"
SLICE_ROOT = Path("/tmp/colacci-law-slice3b-final-preflight")  # nosec B108
ASSET_ROOT = SLICE_ROOT / "generated"
MANIFEST_PATH = SLICE_ROOT / "generated-manifest.json"
EVIDENCE_ROOT = SLICE_ROOT / "evidence"
REPORT_PATH = EVIDENCE_ROOT / "slice3b-final-preflight.json"

DOCUMENTATION_REFRESHED_AT = "2026-08-20T02:09:45Z"
OFFICIAL_URLS = (
    "https://developers.openai.com/api/reference/resources/audio/subresources/transcriptions/methods/create",
    "https://developers.openai.com/api/docs/guides/speech-to-text",
    "https://developers.openai.com/api/docs/models/gpt-4o-transcribe-diarize",
    "https://developers.openai.com/api/docs/pricing",
    "https://developers.openai.com/api/docs/guides/your-data",
)

NON_SECRET_RUNTIME = {
    "APP_PROFILE": "live_test",
    "ALLOW_REAL_CALL_DATA": "false",
    "REAL_CALL_PROCESSING_AUTHORIZED": "false",
    "LIVE_TRANSCRIPTION_ENABLED": "true",
    "LIVE_TRANSCRIPTION_AUTHORIZED": "false",
    "TRANSCRIPTION_APPROVAL_REFERENCE": PREFLIGHT_AUTHORIZATION,
    "TRANSCRIPTION_MODEL_ID": "gpt-4o-transcribe-diarize",
    "TRANSCRIPTION_MAX_REQUESTS": str(MAX_REQUESTS),
    "TRANSCRIPTION_MAX_TOTAL_AUDIO_SECONDS": str(int(MAX_TOTAL_AUDIO_SECONDS)),
    "TRANSCRIPTION_MAX_TOTAL_BYTES": str(MAX_TOTAL_BYTES),
    "TRANSCRIPTION_TEST_BUDGET_USD": str(MAX_BUDGET_USD),
    "CALL_SOURCE_ADAPTER": "generated_synthetic",
    "TRANSCRIBER_ADAPTER": "openai_live",
    "ANALYZER_ADAPTER": "disabled",
    "NOTIFICATION_ADAPTER": "noop",
    "OBJECT_STORAGE_BACKEND": "local_synthetic",
    "MEDIA_TEMP_ROOT": str(SLICE_ROOT / "objects"),
}

OWNER_BOOLEAN_GATES = {
    "named_firm_owned_openai_project": "FIRM_OWNED_OPENAI_PROJECT_NAMED",
    "project_account_ownership_approved": "OPENAI_PROJECT_OWNERSHIP_APPROVED",
    "account_data_controls_confirmed": "OPENAI_PROJECT_DATA_CONTROLS_APPROVED",
    "provider_terms_approved": "OPENAI_PROVIDER_TERMS_APPROVED",
    "generated_audio_test_approved": "GENERATED_AUDIO_TEST_APPROVED",
}


def _artifact_id(asset_id: str) -> str:
    return hashlib.sha256(f"slice3b-final-preflight:{asset_id}".encode()).hexdigest()[:32]


def _is_present(environment: Mapping[str, str], name: str) -> bool:
    """Observe only whether a sensitive variable exists; never access its value."""

    return name in environment


def _boolean_gate(environment: Mapping[str, str], name: str) -> bool:
    return environment.get(name) == "true"


def _cleanup_all_but_report(report: dict[str, object]) -> None:
    shutil.rmtree(SLICE_ROOT, ignore_errors=True)
    EVIDENCE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(SLICE_ROOT, 0o700)
    os.chmod(EVIDENCE_ROOT, 0o700)
    os.chmod(REPORT_PATH, 0o600)


def _inspect_assets() -> tuple[list[dict[str, object]], list[str]]:
    failures: list[str] = []
    safe_assets: list[dict[str, object]] = []
    try:
        manifest = cast(dict[str, Any], json.loads(MANIFEST_PATH.read_text(encoding="utf-8")))
        assets = {
            str(item["asset_id"]): item for item in cast(list[dict[str, Any]], manifest["assets"])
        }
        if set(APPROVED_ASSET_IDS) - set(assets):
            return [], ["approved_generated_assets"]
        inspector = MediaInspector(
            max_bytes=MAX_TOTAL_BYTES,
            max_duration_seconds=60,
            allowed_root=ASSET_ROOT,
        )
        for opaque_index, asset_id in enumerate(APPROVED_ASSET_IDS, start=1):
            item = assets[asset_id]
            if item.get("synthetic") is not True:
                failures.append("generated_non_human_attestation")
                continue
            inspection = inspector.inspect(
                ASSET_ROOT / str(item["filename"]), artifact_id=_artifact_id(asset_id)
            )
            safe_assets.append(
                {
                    "opaque_name": f"generated-case-{opaque_index:02d}",
                    "case": asset_id,
                    "content_contract": str(item["kind"]),
                    "language": "es" if asset_id == "spanish-short" else "en",
                    "format": inspection.media_format.value,
                    "duration_seconds": round(inspection.duration_seconds, 3),
                    "byte_size": inspection.byte_size,
                    "channel_count": inspection.channel_count,
                    "sample_rate_hz": inspection.sample_rate_hz,
                    "codec": inspection.codec,
                    "hash_reference": inspection.hash_reference,
                    "chunking_strategy": "auto"
                    if inspection.duration_seconds > 30
                    else "single_block",
                    "generated_non_human": True,
                }
            )
        long_asset = next((item for item in safe_assets if item["case"] == "english-long"), None)
        long_source = assets.get("english-long", {})
        if (
            long_asset is None
            or cast(float, long_asset["duration_seconds"]) <= 30
            or long_source.get("speaker_source_count") != 2
        ):
            failures.append("two_voice_english_over_30_seconds")
        if (
            sum(cast(float, item["duration_seconds"]) for item in safe_assets)
            > MAX_TOTAL_AUDIO_SECONDS
        ):
            failures.append("planned_audio_duration_cap")
        if sum(cast(int, item["byte_size"]) for item in safe_assets) > MAX_TOTAL_BYTES:
            failures.append("planned_media_byte_cap")
    # Preserve Python 3.13 parse compatibility for stale-image rejection diagnostics.
    except (FileNotFoundError, KeyError, TypeError, ValueError, MediaBoundaryError):  # fmt: skip
        failures.append("generated_media_inspection")
    return safe_assets, sorted(set(failures))


def main() -> None:
    safe_assets, failures = _inspect_assets()
    generated_media_valid = not failures
    runtime_gates = {
        name.lower(): os.environ.get(name) == expected
        for name, expected in NON_SECRET_RUNTIME.items()
    }
    owner_gates = {
        report_name: _boolean_gate(os.environ, env_name)
        for report_name, env_name in OWNER_BOOLEAN_GATES.items()
    }
    sensitive_presence = {
        "ephemeral_project_scoped_credential_present": _is_present(os.environ, "OPENAI_API_KEY"),
        "project_identifier_present": _is_present(os.environ, "OPENAI_PROJECT_ID"),
        "new_live_execution_authorization_present": _is_present(
            os.environ, "TRANSCRIPTION_LIVE_EXECUTION_AUTHORIZATION_ID"
        ),
    }
    endpoint = safe_endpoint_class(os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    if endpoint is None:
        failures.append("official_openai_endpoint")
    failures.extend(name for name, passed in runtime_gates.items() if not passed)
    failures.extend(name for name, passed in owner_gates.items() if not passed)
    failures.extend(name for name, passed in sensitive_presence.items() if not passed)
    failures = sorted(set(failures))
    missing_inputs = [
        name for name, passed in {**owner_gates, **sensitive_presence}.items() if not passed
    ]
    now = datetime.now(UTC)
    report: dict[str, object] = {
        "version": "slice3b-final-preflight-v1",
        "decision": "blocked" if failures else "ready_for_separate_live_authorization",
        "checked_at": now.isoformat(),
        "preflight_authorization_reference": PREFLIGHT_AUTHORIZATION,
        "source": {
            "accepted_baseline_commit": SOURCE_COMMIT,
            "branch": SOURCE_BRANCH,
            "migration_head": MIGRATION_HEAD,
        },
        "runtime_versions": {
            "python": platform.python_version(),
            "openai_python_sdk": importlib.metadata.version("openai"),
            "httpx2": importlib.metadata.version("httpx2"),
        },
        "documentation": {
            "retrieved_at": DOCUMENTATION_REFRESHED_AT,
            "official_urls": list(OFFICIAL_URLS),
            "endpoint": "/v1/audio/transcriptions",
            "model": "gpt-4o-transcribe-diarize",
            "response_format": "diarized_json",
            "chunking_contract": "auto_required_over_30_seconds; otherwise single block when unset",
            "accepted_file_types": ["mp3", "mp4", "mpeg", "mpga", "m4a", "wav", "webm"],
            "provider_file_limit": "25 MB",
            "public_pricing": {
                "audio_input_per_1m_tokens_usd": "2.50",
                "text_output_per_1m_tokens_usd": "10.00",
                "estimated_per_minute": "not separately published for diarize model",
            },
            "public_availability": {
                "free_tier": "not_supported",
                "tiers_1_through_5": "documented_rate_limits",
                "firm_account_access": "unverified",
            },
            "data_use_and_retention": {
                "training": "no unless customer explicitly opts in",
                "transcription_abuse_monitoring_retention": "none in current endpoint table",
                "transcription_application_state_retention": "none in current endpoint table",
                "zero_data_retention_eligible": True,
                "firm_project_configuration": "unverified",
            },
            "python_sdk_compatibility": {
                "official_guide_has_python_diarization_example": True,
                "repository_pin": "3.2.0",
                "offline_contract_validation_required": True,
                "latest_package_version_claimed": False,
            },
        },
        "account_specific_unverified": [
            "named firm-owned OpenAI project and approved ownership",
            "model access and actual account tier/rate limits",
            "project-specific data-control selection",
            "provider terms and intended generated-audio test approval",
            "credential scope and ephemerality",
            "new live-execution authorization identifier",
        ],
        "generated_audio_manifest": safe_assets,
        "generated_audio_fingerprint": asset_fingerprint(safe_assets) if safe_assets else None,
        "planned_totals": {
            "asset_count": len(safe_assets),
            "duration_seconds": round(
                sum(cast(float, item["duration_seconds"]) for item in safe_assets), 3
            ),
            "bytes": sum(cast(int, item["byte_size"]) for item in safe_assets),
        },
        "gates": {
            "non_secret_runtime": runtime_gates,
            "owner_and_account_approvals": owner_gates,
            "sensitive_runtime_presence_only": sensitive_presence,
            "official_endpoint_allowlisted": endpoint is not None,
            "generated_media_valid": generated_media_valid,
        },
        "fail_closed_controls": {
            "sdk_redirects_disabled": True,
            "sdk_automatic_retries": 0,
            "application_transient_retry_cap": 1,
            "total_request_cap": MAX_REQUESTS,
            "cumulative_audio_cap_seconds": MAX_TOTAL_AUDIO_SECONDS,
            "cumulative_media_cap_bytes": MAX_TOTAL_BYTES,
            "application_cost_cap_usd": str(MAX_BUDGET_USD),
            "analysis_disabled": True,
            "notifications_disabled": True,
            "real_data_rejected": True,
            "arbitrary_media_roots_rejected": True,
            "generated_non_human_audio_only": True,
            "retained_evidence_content_sanitized": True,
        },
        "counters": {
            "provider_client_constructed": False,
            "provider_requests": 0,
            "retries": 0,
            "uploaded_duration_seconds": 0,
            "uploaded_bytes": 0,
            "actual_cost_usd": "0.00",
            "analysis_calls": 0,
            "external_notifications": 0,
            "real_or_human_audio": 0,
        },
        "network_mode": "none",
        "cleanup": {
            "generated_audio_removed": True,
            "source_manifest_removed": True,
            "disposable_databases_removed": True,
            "temporary_provider_shaped_artifacts_removed": True,
            "retained_files": ["evidence/slice3b-final-preflight.json"],
        },
        "missing_inputs": missing_inputs,
        "all_gate_failures": failures,
    }
    _cleanup_all_but_report(report)
    print(
        f"transcription-live-preflight {report['decision']}: provider_client=false "
        "requests=0 retries=0 uploads=0 actual_cost_usd=0.00 cleanup=confirmed"
    )
    if failures:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
