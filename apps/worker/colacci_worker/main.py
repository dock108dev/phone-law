"""Content-free worker health process; job processing begins in a later slice."""

from __future__ import annotations

import json
import re
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import BaseModel, ValidationError
from sqlalchemy import Engine

from apps.worker.colacci_worker.health import liveness_payload, readiness_payload
from packages.config import Settings
from packages.database.health import create_database_engine
from packages.observability.logging import (
    OperationalLogger,
    configure_logging,
    emit_startup_rejection,
    normalize_correlation_id,
)


class WorkerHealthServer(ThreadingHTTPServer):
    settings: Settings
    engine: Engine
    operational_logger: OperationalLogger


class HealthHandler(BaseHTTPRequestHandler):
    server: WorkerHealthServer
    _CORRELATION_HEADER_PATTERN = re.compile(r"^[A-Za-z0-9._-]{8,64}$")

    def _header_safe_correlation_id(self, candidate: str) -> str:
        if self._CORRELATION_HEADER_PATTERN.fullmatch(candidate):
            return candidate
        return uuid4().hex

    def do_GET(self) -> None:
        route = urlsplit(self.path).path
        correlation_id = normalize_correlation_id(self.headers.get("X-Correlation-ID"))

        if route == "/health/live":
            self._write_json(HTTPStatus.OK, liveness_payload(self.server.settings), correlation_id)
            return

        if route == "/health/ready":
            status_code, payload, error_code = readiness_payload(
                self.server.settings,
                self.server.engine,
            )
            if error_code:
                self.server.operational_logger.event(
                    "readiness_failed",
                    level="warning",
                    component="database",
                    correlation_id=correlation_id,
                    error_code=error_code,
                    status="not_ready",
                )
            self._write_json(HTTPStatus(status_code), payload, correlation_id)
            return

        self._write_json(
            HTTPStatus.NOT_FOUND,
            {"status": "not_found"},
            correlation_id,
        )

    def log_message(self, _: str, *args: object) -> None:
        """Disable the default content-bearing HTTP access log."""

    def _write_json(
        self,
        status_code: HTTPStatus,
        payload: BaseModel | dict[str, str],
        correlation_id: str,
    ) -> None:
        content = payload.model_dump() if isinstance(payload, BaseModel) else payload
        encoded = json.dumps(content, separators=(",", ":")).encode("utf-8")
        safe_correlation_id = self._header_safe_correlation_id(correlation_id)
        self.send_response(status_code.value)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("X-Correlation-ID", safe_correlation_id)
        self.end_headers()
        self.wfile.write(encoded)
        self.server.operational_logger.event(
            "worker_health_request_completed",
            correlation_id=safe_correlation_id,
            method="GET",
            route=urlsplit(self.path).path,
            status=str(status_code.value),
        )


def main() -> None:
    try:
        settings = Settings(service_name="worker")
    except (ValidationError, ValueError):
        emit_startup_rejection("worker")
        sys.exit(78)

    configure_logging(settings.log_level)
    logger = OperationalLogger("worker", settings.log_level)
    engine = create_database_engine(settings.sqlalchemy_database_url)
    # Listen across the container network; Compose publishes the host port on loopback only.
    server = WorkerHealthServer(
        ("0.0.0.0", 8001),  # noqa: S104
        HealthHandler,
    )
    server.settings = settings
    server.engine = engine
    server.operational_logger = logger
    logger.event(
        "service_started",
        component="health_server",
        profile=settings.app_profile.value,
        status="up",
        version=settings.app_version,
    )
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        engine.dispose()
        server.server_close()
        logger.event("service_stopped", component="health_server", status="stopped")


if __name__ == "__main__":
    main()
