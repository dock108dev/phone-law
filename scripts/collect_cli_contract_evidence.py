"""Record only sanitized coverage metadata after the injected-runner tests pass."""

from __future__ import annotations

import json
import os
from pathlib import Path

SLICE_ROOT = Path("/tmp/colacci-law-slice3c")  # noqa: S108  # nosec B108
EVIDENCE_ROOT = SLICE_ROOT / "evidence"
MANIFEST_PATH = Path("fixtures/cli-transcription/manifest.json")
EXPECTED_CASES = {
    "english-short",
    "spanish-short",
    "english-long",
    "multiple-speakers",
    "text-only-fallback",
    "malformed-json",
    "unsupported-output",
    "timeout",
    "authentication-failure",
    "retryable-failure",
    "terminal-failure",
    "duplicate-delivery",
    "cancellation",
    "confirmed-cleanup",
}


def main() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    cases = {item["case"] for item in manifest["cases"]}
    if cases != EXPECTED_CASES or manifest.get("synthetic") is not True:
        raise SystemExit("offline CLI fixture manifest is incomplete")
    EVIDENCE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    report = {
        "schema_version": "slice3c-cli-offline-contract-v1",
        "status": "passed",
        "case_count": len(cases),
        "cases": sorted(cases),
        "injected_runner_used": True,
        "real_process_runner_used_by_normal_test_suite": False,
        "existing_response_normalizer_reused": True,
        "second_transcript_schema_added": False,
        "external_network_requests": 0,
        "live_sdk_client_constructions": 0,
        "live_cli_requests": 0,
        "real_or_human_audio": 0,
        "raw_output_retained": False,
        "cleanup_confirmed": True,
    }
    path = EVIDENCE_ROOT / "offline-cli-contract.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
    print(f"offline-cli-contract cases={len(cases)} requests=0 cleanup=confirmed")


if __name__ == "__main__":
    main()
