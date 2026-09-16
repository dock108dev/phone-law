"""Reject unapproved browser mutation origins before parsing or route side effects."""

from __future__ import annotations

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from apps.api.colacci_api.errors import error_response
from packages.observability.logging import OperationalLogger


class MutationOriginMiddleware:
    def __init__(
        self, app: ASGIApp, *, allowed_origins: list[str], logger: OperationalLogger
    ) -> None:
        self.app = app
        self.allowed_origins = frozenset(allowed_origins) - {"null", "*", ""}
        self.logger = logger

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] not in {"GET", "HEAD", "OPTIONS"}:
            origins = [value for key, value in scope["headers"] if key.lower() == b"origin"]
            if origins:
                request = Request(scope)
                # TrustedHostMiddleware must run first. Preserve the browser-facing
                # Host/port through the local Vite proxy; never trust X-Forwarded-Host.
                same_origin = f"{request.url.scheme}://{request.url.netloc}"
                origin = origins[0].decode("latin-1")
                if len(origins) != 1 or (
                    origin != same_origin and origin not in self.allowed_origins
                ):
                    correlation_id = scope.get("state", {}).get(
                        "correlation_id", "correlation-unavailable"
                    )
                    self.logger.event(
                        "mutation_origin_rejected",
                        level="warning",
                        correlation_id=correlation_id,
                        error_code="mutation_origin_forbidden",
                        status="rejected",
                    )
                    await error_response(403, "mutation_origin_forbidden", correlation_id)(
                        scope, receive, send
                    )
                    return
        # Origin-less CLI requests still require the normal route authorization.
        await self.app(scope, receive, send)
