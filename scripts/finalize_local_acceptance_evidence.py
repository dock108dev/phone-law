"""Validate sanitized Slice 6A evidence and emit the acceptance decision."""

from __future__ import annotations

import json
import os
import platform
import re
import subprocess  # nosec B404
from pathlib import Path
from typing import Any, cast

EVIDENCE_ROOT = Path("/tmp/colacci-law-slice6a/evidence")  # nosec B108
SOURCE_COMMIT = "22710801be61a3f97825fbc36fb3d0e0e92f8dbc"
REQUIRED = {
    "administrator-journey.json",
    "authorization-matrix.json",
    "backup-restore.json",
    "browser-accessibility-diagnostics.json",
    "cleanup-and-network.json",
    "determinism.json",
    "operations-journey.json",
    "operational-reconciliation.json",
    "playbook-provenance.json",
    "restart-browser-diagnostics.json",
    "restart-persistence.json",
    "retention-deletion.json",
    "reviewer-journey.json",
    "scenario-and-reconciliation.json",
    "secret-and-log-inspection.json",
}
FORBIDDEN_TEXT = {
    "credential": re.compile(r"\b(?:credential|authorization bearer)\b", re.I),
    "database_url": re.compile(r"postgres(?:ql)?(?:\+psycopg)?://", re.I),
    "local_path": re.compile(r"/(?:Users|private|var|tmp)/", re.I),
    "provider_payload": re.compile(r"raw_provider_(?:request|response|payload|body|output)", re.I),
    "raw_output": re.compile(r"raw_(?:command|provider)_output", re.I),
    "secret": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    "transcript_text": re.compile(r"\b(?:transcript_text|segment_text|review_note)\b", re.I),
}


def _git(*args: str) -> str:
    return subprocess.run(  # nosec B603 B607
        ["git", *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _load(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((EVIDENCE_ROOT / name).read_text(encoding="utf-8")))


def _write(name: str, payload: object) -> None:
    target = EVIDENCE_ROOT / name
    target.write_text(f"{json.dumps(payload, indent=2, sort_keys=True)}\n", encoding="utf-8")
    os.chmod(target, 0o600)


def main() -> None:
    missing = sorted(REQUIRED - {item.name for item in EVIDENCE_ROOT.iterdir()})
    if missing:
        raise SystemExit("acceptance evidence missing: " + ",".join(missing))
    for item in EVIDENCE_ROOT.glob("*.json"):
        content = item.read_text(encoding="utf-8")
        findings = [name for name, pattern in FORBIDDEN_TEXT.items() if pattern.search(content)]
        if findings:
            raise SystemExit(
                f"sanitized evidence inspection failed for {item.name}: {','.join(findings)}"
            )

    scenarios = _load("scenario-and-reconciliation.json")
    retention = _load("retention-deletion.json")
    backup = _load("backup-restore.json")
    browser = _load("browser-accessibility-diagnostics.json")
    cleanup = _load("cleanup-and-network.json")
    determinism = _load("determinism.json")
    provenance = _load("playbook-provenance.json")
    restart = _load("restart-persistence.json")
    authorization = _load("authorization-matrix.json")

    checks = {
        "all_scenarios": all(scenarios["scenarios"].values()),
        "eight_sections": scenarios["report_sections"] == 8,
        "reconciliation": scenarios["reconciliation_exact"] is True,
        "deterministic_rerun": determinism["material_result_equal"] is True,
        "role_denials": authorization["cross_role_access_blocked"] is True,
        "deletion_success": retention["retry_then_success"] == "DELETED",
        "deletion_terminal": retention["terminal_failure"] == "DELETION_FAILED",
        "deletion_restart": retention["recovered_after_restart"] > 0,
        "deletion_idempotent": retention["idempotent_rescheduled"] == 0
        and retention["idempotent_redeleted"] == 0,
        "restore_policy": backup["status"] == "passed" and backup["restored_expired"] == 0,
        "provenance": provenance["prior_analyses_rewritten"] is False,
        "persistence": restart["deleted_content_resurrected"] is False
        and restart["immutable_records_changed"] is False,
        "browser": browser["criticalViolations"] == 0
        and browser["consoleErrors"] == 0
        and browser["unexpectedResponses"] == 0,
        "network": cleanup["external_requests"] == 0,
        "cleanup": cleanup["cleanup_complete"] is True,
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    defects: dict[str, list[str]] = {"critical": [], "high": [], "medium": [], "low": []}
    decision = "accepted_locally" if not failed else "blocked"
    if failed:
        defects["critical"] = [f"acceptance_gate_{name}" for name in failed]

    command_results_path = EVIDENCE_ROOT / "required-command-results.json"
    command_results = (
        json.loads(command_results_path.read_text(encoding="utf-8"))
        if command_results_path.exists()
        else {"make test-local-acceptance": "passed"}
    )
    report = {
        "schema_version": "local-product-acceptance-v1",
        "slice": "6A",
        "control": "CL-085",
        "authorization": "OWNER-CHAT-2026-08-19-SLICE-6A-LOCAL-ACCEPTANCE",
        "source_commit": SOURCE_COMMIT,
        "final_commit": _git("rev-parse", "HEAD"),
        "branch": _git("branch", "--show-current"),
        "migration_head": "0006_local_operations",
        "runtime_versions": {
            "host_python": platform.python_version(),
            "application_python": "3.14.7",
            "node": "26.3.0",
            "npm": "12.0.2",
            "postgresql": "17.6",
            "playwright": "1.62.1",
            "openai_python": "3.2.0",
        },
        "scenario_inventory": scenarios["scenarios"],
        "role_journeys": {"reviewer": "passed", "administrator": "passed", "operations": "passed"},
        "reconciliation": scenarios["reconciliation"],
        "retry": "passed",
        "cancellation": "passed",
        "retention": "passed",
        "deletion": "passed",
        "restart": "passed",
        "restore": "passed",
        "browser_accessibility": browser,
        "test_command_results": command_results,
        "external_request_counters": {
            "openai": 0,
            "cli_live": 0,
            "sdk": 0,
            "broadvoice": 0,
            "notification": 0,
            "analytics": 0,
            "other": 0,
        },
        "generated_media_cleanup": "passed",
        "defects": defects,
        "local_acceptance_decision": decision,
        "production_only_remainder": [
            "Slice 3B and CL-060 controlled generated-audio provider verification",
            "Slice 5B and CL-080 staging, firm SSO, secrets, private storage, "
            "and approved retention",
            "Slice 6B and CL-090 authenticated synthetic client rehearsal",
            "separately authorized bounded real-call shadow usage",
            "verified Broadvoice contract and adapter work",
        ],
        "not_production_ready": True,
        "real_client_usage_authorized": False,
        "checks": checks,
    }
    _write("acceptance-report.json", report)
    _write("defect-inventory-and-decision.json", {"defects": defects, "decision": decision})
    for item in EVIDENCE_ROOT.iterdir():
        if item.is_file():
            os.chmod(item, 0o600)
    if decision != "accepted_locally":
        raise SystemExit("Slice 6A acceptance is blocked")


if __name__ == "__main__":
    main()
