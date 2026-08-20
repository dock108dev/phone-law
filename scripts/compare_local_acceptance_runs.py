"""Compare the material, content-free results of two Slice 6A rehearsals."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _material(root: Path) -> dict[str, object]:
    scenarios = json.loads((root / "scenario-and-reconciliation.json").read_text())
    retention = json.loads((root / "retention-deletion.json").read_text())
    backup = json.loads((root / "backup-restore.json").read_text())
    return {
        "scenarios": scenarios["scenarios"],
        "report_sections": scenarios["report_sections"],
        "reconciliation": scenarios["reconciliation"],
        "retry_then_success": retention["retry_then_success"],
        "terminal_failure": retention["terminal_failure"],
        "restart_recovered": retention["recovered_after_restart"] > 0,
        "idempotent": retention["idempotent_rescheduled"] == 0
        and retention["idempotent_redeleted"] == 0,
        "restore_status": backup["status"],
        "restore_expired": backup["restored_expired"],
        "cleanup": retention["generated_media_cleanup_confirmed"],
    }


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("usage: compare_local_acceptance_runs.py RUN1 RUN2 OUTPUT")
    first = _material(Path(sys.argv[1]))
    second = _material(Path(sys.argv[2]))
    if first != second:
        raise SystemExit("local acceptance material result changed between deterministic runs")
    output = Path(sys.argv[3])
    result = {
        "result": "passed",
        "runs": 2,
        "material_result_equal": True,
        "material": first,
    }
    output.write_text(
        f"{json.dumps(result, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )
    os.chmod(output, 0o600)


if __name__ == "__main__":
    main()
