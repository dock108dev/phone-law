"""Run the exact Slice 3C acceptance matrix and retain machine-readable results."""

from __future__ import annotations

import json
import os

# Only the fixed local command matrix below is executed.
import subprocess  # nosec B404
import time
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = Path("/tmp/colacci-law-slice3c/evidence")  # noqa: S108  # nosec B108
COMMANDS = (
    ("make bootstrap", ("make", "bootstrap")),
    ("make transcription-cli-preflight", ("make", "transcription-cli-preflight")),
    ("make test-transcription-cli-offline", ("make", "test-transcription-cli-offline")),
    ("make seed-demo", ("make", "seed-demo")),
    ("make lint", ("make", "lint")),
    ("make typecheck", ("make", "typecheck")),
    ("make test", ("make", "test")),
    ("make test-integration", ("make", "test-integration")),
    ("make test-fixtures", ("make", "test-fixtures")),
    ("make test-e2e", ("make", "test-e2e")),
    ("make smoke", ("make", "smoke")),
    ("make audit", ("make", "audit")),
)


def _write(payload: dict[str, object]) -> None:
    EVIDENCE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = EVIDENCE_ROOT / "validation-results.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def main() -> None:
    started_at = datetime.now(UTC)
    results: list[dict[str, object]] = []
    for label, command in COMMANDS:
        print(f"slice3c-validation starting={label}", flush=True)
        started = time.monotonic()
        completed = subprocess.run(  # noqa: S603  # nosec B603
            command,
            cwd=REPOSITORY_ROOT,
            check=False,
        )
        result = {
            "command": label,
            "exit_code": completed.returncode,
            "status": "passed" if completed.returncode == 0 else "failed",
            "duration_seconds": round(time.monotonic() - started, 3),
        }
        results.append(result)
        if completed.returncode != 0:
            _write(
                {
                    "schema_version": "slice3c-validation-results-v1",
                    "status": "failed",
                    "started_at": started_at.isoformat(),
                    "completed_at": datetime.now(UTC).isoformat(),
                    "results": results,
                }
            )
            raise SystemExit(completed.returncode)
    _write(
        {
            "schema_version": "slice3c-validation-results-v1",
            "status": "passed",
            "started_at": started_at.isoformat(),
            "completed_at": datetime.now(UTC).isoformat(),
            "required_command_count": len(COMMANDS),
            "passed_command_count": len(results),
            "results": results,
        }
    )
    print(f"slice3c-validation status=passed commands={len(results)}", flush=True)


if __name__ == "__main__":
    main()
