"""Sanitized, no-request Slice 3C host CLI capability preflight."""

from __future__ import annotations

import json
import os
import re

# Capability probes use only fixed executable paths and argument arrays.
import subprocess  # nosec B404
from pathlib import Path

SLICE_ROOT = Path("/tmp/colacci-law-slice3c")  # noqa: S108  # nosec B108
EVIDENCE_ROOT = SLICE_ROOT / "evidence"
REPORT_PATH = EVIDENCE_ROOT / "cli-preflight.json"
DECLARED_VERSION = "1.6.0"
SAFE_CANDIDATES = (
    (Path("/opt/homebrew/bin/openai"), "homebrew_standard"),
    (Path("/usr/local/bin/openai"), "usr_local_standard"),
    (Path("/usr/bin/openai"), "system_standard"),
)
ROOT_HELP_MARKERS = (
    "audio:transcriptions",
    "--format",
)
TRANSCRIPTION_HELP_MARKERS = (
    "audio:transcriptions create",
    "--model",
    "--file",
    "--response-format",
    "--chunking-strategy",
)


def _bounded_local_command(executable: Path, arguments: tuple[str, ...]) -> tuple[int, bytes]:
    child_environment = {
        "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
        "LANG": "C",
        "LC_ALL": "C",
        "NO_COLOR": "1",
    }
    try:
        completed = subprocess.run(  # noqa: S603  # nosec B603
            [str(executable), *arguments],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            env=child_environment,
            cwd="/tmp",  # noqa: S108  # nosec B108
            timeout=3,
            check=False,
        )
    # Preserve Python 3.13 parse compatibility for stale-image rejection diagnostics.
    except (OSError, subprocess.TimeoutExpired):  # fmt: skip
        return 127, b""
    combined = completed.stdout + completed.stderr
    if len(combined) > 128 * 1024:
        return 126, b""
    return completed.returncode, combined


def _capability() -> dict[str, object]:
    candidate: Path | None = None
    classification = "unavailable"
    for path, path_classification in SAFE_CANDIDATES:
        if path.is_file() and os.access(path, os.X_OK):
            candidate = path
            classification = path_classification
            break
    observed = "unavailable"
    surface = False
    if candidate is not None:
        version_code, version_output = _bounded_local_command(candidate, ("--version",))
        match = re.search(rb"(?<![0-9])([0-9]+\.[0-9]+\.[0-9]+)(?![0-9])", version_output)
        if version_code == 0 and match:
            observed = match.group(1).decode("ascii")
        root_help_code, root_help_output = _bounded_local_command(candidate, ("--help",))
        transcription_help_code, transcription_help_output = _bounded_local_command(
            candidate, ("audio:transcriptions", "create", "--help")
        )
        root_help_text = root_help_output.decode("utf-8", errors="ignore")
        transcription_help_text = transcription_help_output.decode("utf-8", errors="ignore")
        surface = (
            root_help_code == 0
            and transcription_help_code == 0
            and all(marker in root_help_text for marker in ROOT_HELP_MARKERS)
            and all(marker in transcription_help_text for marker in TRANSCRIPTION_HELP_MARKERS)
        )
    state = (
        "supported"
        if observed == DECLARED_VERSION and surface
        else ("unavailable" if candidate is None else "unsupported")
    )
    return {
        "path_classification": classification,
        "observed_version": observed,
        "command_surface_supported": surface,
        "state": state,
    }


def main() -> None:
    EVIDENCE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(SLICE_ROOT, 0o700)
    os.chmod(EVIDENCE_ROOT, 0o700)
    capability = _capability()
    report = {
        "schema_version": "slice3c-cli-preflight-v1",
        "execution_profile": "local_dev",
        "cli_path_classification": capability["path_classification"],
        "declared_cli_version": DECLARED_VERSION,
        "declared_cli_contract_version": "openai-cli-audio-transcriptions-v1",
        "observed_cli_version": capability["observed_version"],
        "cli_state": capability["state"],
        "supported_command_surface": capability["command_surface_supported"],
        "command_surface_contract": "audio-transcriptions-create-diarized-json-chunking-auto-v1",
        "generated_only_boundary": True,
        "credential_present": "OPENAI_API_KEY" in os.environ,
        "project_configuration_present": "OPENAI_PROJECT_ID" in os.environ,
        "selected_deterministic_fallback": "fixture-and-transcript-only",
        "live_execution_disabled": True,
        "network_operation_allowed": False,
        "provider_client_constructed": False,
        "request_count": 0,
        "retry_count": 0,
        "uploaded_bytes": 0,
        "uploaded_seconds": 0,
        "cost_usd": "0.00",
    }
    report["official_contract_refreshed_on"] = "2026-08-17"
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(REPORT_PATH, 0o600)
    print(
        "cli-preflight "
        f"state={report['cli_state']} observed={report['observed_cli_version']} "
        "fallback=fixture-and-transcript-only requests=0"
    )


if __name__ == "__main__":
    main()
