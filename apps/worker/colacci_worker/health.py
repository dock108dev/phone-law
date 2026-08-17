"""Worker liveness and readiness behavior."""

from __future__ import annotations

from sqlalchemy import Engine

from packages.config import Settings
from packages.contracts.health import HealthResponse
from packages.database.health import database_readiness


def liveness_payload(settings: Settings) -> HealthResponse:
    return HealthResponse(
        status="up",
        service="worker",
        profile=settings.app_profile.value,
        version=settings.app_version,
        synthetic_data=settings.synthetic_mode,
        database="not_checked",
        migration="not_checked",
    )


def readiness_payload(settings: Settings, engine: Engine) -> tuple[int, HealthResponse, str | None]:
    result = database_readiness(engine)
    payload = HealthResponse(
        status="ready" if result.ready else "not_ready",
        service="worker",
        profile=settings.app_profile.value,
        version=settings.app_version,
        synthetic_data=settings.synthetic_mode,
        database="ready" if result.connected else "not_ready",
        migration="current" if result.migration_current else "not_current",
    )
    return (200 if result.ready else 503, payload, result.error_code)
