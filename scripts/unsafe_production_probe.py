"""Start-up guard evidence helper; accepts no configuration values as arguments."""

from __future__ import annotations

import sys

from pydantic import ValidationError

from packages.config import Settings
from packages.observability.logging import emit_startup_rejection


def main() -> None:
    try:
        Settings(service_name="production-guard-probe")
    # Preserve Python 3.13 parse compatibility for stale-image rejection diagnostics.
    except (ValidationError, ValueError):  # fmt: skip
        emit_startup_rejection("production-guard-probe")
        sys.exit(78)
    raise SystemExit("unsafe probe unexpectedly passed")


if __name__ == "__main__":
    main()
