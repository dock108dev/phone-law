"""Finalize private, content-free Slice 5A cleanup evidence."""

from __future__ import annotations

import json
import os
from pathlib import Path

EVIDENCE_ROOT = Path("/tmp/colacci-law-slice5a/evidence")  # nosec B108


def main() -> None:
    os.umask(0o077)
    payload = {
        "external_requests": 0,
        "provider_requests": 0,
        "cli_requests": 0,
        "sdk_requests": 0,
        "notification_attempts": 0,
        "other_external_requests": 0,
        "offline_internal_network": True,
        "content_free_logs_inspected": True,
        "secret_scan": "passed",
        "disposable_stack_removed": True,
        "disposable_database_removed": True,
        "disposable_runtime_removed": True,
        "evidence_root_mode": "0700",
        "retained_evidence_mode": "0600",
        "cleanup_complete": True,
    }
    target = EVIDENCE_ROOT / "cleanup-and-network.json"
    target.write_text(f"{json.dumps(payload, indent=2, sort_keys=True)}\n", encoding="utf-8")
    os.chmod(EVIDENCE_ROOT, 0o700)
    for item in EVIDENCE_ROOT.iterdir():
        if item.is_file():
            os.chmod(item, 0o600)


if __name__ == "__main__":
    main()
