"""Validated API process entry point."""

from __future__ import annotations

import sys

import uvicorn
from pydantic import ValidationError

from apps.api.colacci_api.app import create_app
from packages.config import Settings
from packages.observability.logging import configure_logging, emit_startup_rejection


def main() -> None:
    try:
        settings = Settings(service_name="api")
    except (ValidationError, ValueError):
        emit_startup_rejection("api")
        sys.exit(78)

    configure_logging(settings.log_level)
    uvicorn.run(
        create_app(settings),
        # Listen across the container network; Compose publishes the host port on loopback only.
        host="0.0.0.0",  # noqa: S104
        port=8000,
        access_log=False,
        log_config=None,
    )


if __name__ == "__main__":
    main()
