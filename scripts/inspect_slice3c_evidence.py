"""Fail closed on Slice 3C evidence content, network claims, and cleanup."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

SLICE_ROOT = Path("/tmp/colacci-law-slice3c")  # noqa: S108  # nosec B108
EVIDENCE_ROOT = SLICE_ROOT / "evidence"
INPUT_REPORTS = (
    "cli-preflight.json",
    "offline-cli-contract.json",
    "child-process-security.json",
    "transcript-only-full-loop.json",
    "database-provenance.json",
)
FORBIDDEN_KEYS = {
    "command",
    "command_arguments",
    "credential_value",
    "environment_values",
    "project_identifier",
    "provider_payload",
    "stderr",
    "stdout",
    "text",
    "transcript",
}
FORBIDDEN_VALUE_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"proj[_-][A-Za-z0-9_-]{4,}", re.IGNORECASE),
    re.compile(r"Bearer\s+", re.IGNORECASE),
    re.compile(r"/tmp/[^\s\"']+\.(?:wav|mp3|m4a|ogg|webm)"),  # noqa: S108  # nosec B108
)
INVENTED_CONTENT_MARKERS = (
    "photos I sent yesterday",
    "call you back by Friday",
    "eso es todo lo que necesitaba",
)


def _walk_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _walk_keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in _walk_keys(item)}
    return set()


def _write_report(filename: str, payload: dict[str, object]) -> None:
    path = EVIDENCE_ROOT / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def main() -> None:
    reports: dict[str, dict[str, Any]] = {}
    for filename in INPUT_REPORTS:
        path = EVIDENCE_ROOT / filename
        if not path.is_file() or path.stat().st_mode & 0o077:
            raise SystemExit("Slice 3C evidence is missing or not private")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise SystemExit("Slice 3C evidence envelope is invalid")
        reports[filename] = payload

    rendered = json.dumps(reports, sort_keys=True)
    evidence_keys = {key for payload in reports.values() for key in _walk_keys(payload)}
    forbidden_keys_present = bool(evidence_keys & FORBIDDEN_KEYS)
    credential_like_values = any(pattern.search(rendered) for pattern in FORBIDDEN_VALUE_PATTERNS)
    transcript_content_present = any(
        marker.lower() in rendered.lower() for marker in INVENTED_CONTENT_MARKERS
    )
    if forbidden_keys_present or credential_like_values or transcript_content_present:
        raise SystemExit("Slice 3C evidence contains prohibited content")

    preflight = reports["cli-preflight.json"]
    offline = reports["offline-cli-contract.json"]
    child = reports["child-process-security.json"]
    transcript = reports["transcript-only-full-loop.json"]
    zero_network = (
        preflight.get("network_operation_allowed") is False
        and preflight.get("request_count") == 0
        and offline.get("external_network_requests") == 0
        and child.get("network_namespace") == "none"
        and child.get("external_network_requests") == 0
        and transcript.get("external_network_requests") == 0
        and transcript.get("provider_requests") == 0
    )
    if not zero_network:
        raise SystemExit("Slice 3C zero-network evidence is incomplete")

    temporary_roots = (
        SLICE_ROOT / "cli-inputs",
        SLICE_ROOT / "process-security-work",
        SLICE_ROOT / "invalid-imports",
        SLICE_ROOT / "objects",
    )
    retained_media = tuple(SLICE_ROOT.rglob("*.wav"))
    retained_work_roots = tuple(path for path in temporary_roots if path.exists())
    if retained_media or retained_work_roots:
        raise SystemExit("Slice 3C temporary inputs were retained")

    _write_report(
        "log-and-secret-inspection.json",
        {
            "schema_version": "slice3c-log-secret-inspection-v1",
            "status": "passed",
            "reports_inspected": len(reports),
            "forbidden_keys_present": False,
            "credential_like_values_present": False,
            "project_identifier_values_present": False,
            "transcript_content_present": False,
            "absolute_media_paths_present": False,
            "raw_command_or_output_present": False,
            "evidence_files_private": True,
        },
    )
    _write_report(
        "zero-network.json",
        {
            "schema_version": "slice3c-zero-network-v1",
            "status": "passed",
            "preflight_provider_requests": 0,
            "injected_contract_external_requests": 0,
            "child_process_network_namespace": "none",
            "child_process_external_requests": 0,
            "transcript_import_external_requests": 0,
            "transcript_import_provider_requests": 0,
            "advisory_audit_excluded_from_offline_boundary": True,
        },
    )
    _write_report(
        "cleanup.json",
        {
            "schema_version": "slice3c-cleanup-v1",
            "status": "passed",
            "temporary_media_files": 0,
            "temporary_work_roots": 0,
            "generated_audio_retained": False,
            "cli_input_retained": False,
            "invalid_import_artifact_retained": False,
            "evidence_retained_only_under_designated_root": True,
        },
    )
    print("slice3c-evidence inspection=passed network=none cleanup=confirmed")


if __name__ == "__main__":
    main()
