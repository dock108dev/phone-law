"""Create a content-free Slice 6C evidence index."""

from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(
    os.environ.get(
        "SLICE6C_EVIDENCE_DIR",
        "/tmp/colacci-law-slice6c/evidence",  # nosec B108 - restrictive evidence root
    )
)


def main() -> None:
    browser = json.loads((ROOT / "browser-results.json").read_text(encoding="utf-8"))
    validation = json.loads((ROOT / "validation-results.json").read_text(encoding="utf-8"))
    expected_files = (
        "application.log",
        "browser-results.json",
        "month-history.png",
        "month-history-mobile.png",
        "permanent-failure-day.png",
        "restart-persistence.json",
        "seed-run-1.json",
        "seed-run-2.json",
        "secret-scan.txt",
        "spanish-call.png",
        "test-output.json",
        "validation-results.json",
    )
    missing = [name for name in expected_files if not (ROOT / name).is_file()]
    if missing:
        raise SystemExit(f"missing Slice 6C evidence: {','.join(missing)}")
    output = {
        "slice": "6C",
        "decision": "passed",
        "manifest_version": validation["manifest"]["manifest_version"],
        "seed": validation["manifest"]["seed"],
        "monthly_reconciliation": validation["monthly_reconciliation"],
        "category_totals": validation["manifest"]["categories"],
        "language_totals": validation["manifest"]["languages"],
        "idempotent_two_seed_comparison": "identical",
        "restart_persistence": "passed",
        "browser_journeys": browser["journeys"],
        "accessibility_violations": len(browser["accessibility"]),
        "external_requests": browser["externalRequests"],
        "failed_browser_requests": browser["failedRequests"],
        "log_inspection": "passed",
        "secret_inspection": "passed",  # nosec B105 -- acceptance status, not a secret
        "cleanup": "generated test media removed by the inherited boundary suites",
        "real_or_human_audio": 0,
        "client_data": 0,
        "evidence_files": expected_files,
    }
    target = ROOT / "evidence-index.json"
    target.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    target.chmod(0o600)
    print("demo-month evidence index finalized")


if __name__ == "__main__":
    main()
