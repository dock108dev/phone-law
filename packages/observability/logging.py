"""Structured content-free logging with an explicit metadata allowlist."""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Final
from uuid import uuid4

SAFE_METADATA_KEYS: Final[frozenset[str]] = frozenset(
    {
        "component",
        "correlation_id",
        "duration_ms",
        "error_code",
        "method",
        "migration_current",
        "profile",
        "route",
        "service",
        "status",
        "version",
    }
)
SAFE_ROUTE_VALUES: Final[frozenset[str]] = frozenset(
    {"/health/live", "/health/ready", "/healthz.json", "/", "/health", "unknown"}
)
CORRELATION_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


class OperationalLogger:
    """Logger that cannot accept arbitrary content fields."""

    def __init__(self, service: str, level: str = "INFO") -> None:
        self.service = _safe_label(service, fallback="application")
        self._logger = logging.getLogger(f"colacci.{self.service}")
        self._logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    def event(self, event: str, *, level: str = "info", **metadata: object) -> None:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": level,
            "event": _safe_label(event, fallback="operational_event"),
            "service": self.service,
        }
        for key, value in metadata.items():
            if key not in SAFE_METADATA_KEYS or key == "service":
                continue
            payload[key] = _safe_metadata_value(key, value)

        log_method = getattr(self._logger, level, self._logger.info)
        log_method(json.dumps(payload, separators=(",", ":"), sort_keys=True))


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    for logger_name in ("uvicorn.access", "uvicorn.error", "sqlalchemy.engine"):
        logging.getLogger(logger_name).disabled = True


def normalize_correlation_id(candidate: str | None) -> str:
    if candidate and CORRELATION_PATTERN.fullmatch(candidate):
        return candidate
    return uuid4().hex


def emit_startup_rejection(service: str) -> None:
    configure_logging("INFO")
    OperationalLogger(service).event(
        "startup_rejected",
        level="error",
        error_code="unsafe_configuration",
        status="rejected",
    )


def _safe_label(value: object, *, fallback: str) -> str:
    text = str(value)
    if re.fullmatch(r"[A-Za-z0-9._/-]{1,64}", text):
        return text
    return fallback


def _safe_metadata_value(key: str, value: object) -> object:
    if key == "route":
        return value if value in SAFE_ROUTE_VALUES else "unknown"
    if key in {"duration_ms"} and isinstance(value, int | float):
        return round(float(value), 3)
    if isinstance(value, bool):
        return value
    return _safe_label(value, fallback="unknown")
