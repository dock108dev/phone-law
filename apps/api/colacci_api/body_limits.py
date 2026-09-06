"""Bound HTTP body consumption without pre-buffering unauthenticated uploads."""

from __future__ import annotations

from fastapi import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from apps.api.colacci_api.errors import error_detail
from packages.manual_upload.request_boundary import MAX_MULTIPART_OVERHEAD
from packages.observability.logging import OperationalLogger
from packages.review.transcript_import import TRANSCRIPT_ONLY_MAX_BYTES

JSON_BODY_MAX_BYTES = 1024 * 1024


class RequestBodyBoundaryError(HTTPException):
    """A content-free rejection that survives route-level error translation."""


class RequestBodyLimitMiddleware:
    def __init__(
        self, app: ASGIApp, *, media_max_bytes: int, logger: OperationalLogger | None = None
    ) -> None:
        self.app = app
        self.logger = logger or OperationalLogger("request_boundary")
        self.audio_limit = media_max_bytes + MAX_MULTIPART_OVERHEAD

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        maximum = (
            self.audio_limit
            if path == "/api/uploads/audio"
            else TRANSCRIPT_ONLY_MAX_BYTES
            if path == "/api/uploads/transcript"
            else JSON_BODY_MAX_BYTES
        )
        correlation_id = scope.get("state", {}).get("correlation_id", "correlation-unavailable")

        def rejection(code: str, status_code: int) -> RequestBodyBoundaryError:
            self.logger.event(
                "request_body_rejected",
                level="warning",
                error_code=code,
                correlation_id=correlation_id,
                status="rejected",
            )
            return RequestBodyBoundaryError(
                status_code=status_code,
                detail=error_detail(code, correlation_id),
            )

        lengths = [value for key, value in scope["headers"] if key.lower() == b"content-length"]
        error: RequestBodyBoundaryError | None = None
        if lengths:
            if len(lengths) != 1 or not lengths[0].isdigit() or len(lengths[0]) > 20:
                error = rejection("invalid_content_length", 400)
            elif int(lengths[0]) > maximum:
                error = rejection("request_body_too_large", 413)
        if error is not None:
            await JSONResponse(status_code=error.status_code, content={"detail": error.detail})(
                scope, receive, send
            )
            return

        consumed = 0

        async def bounded_receive() -> Message:
            nonlocal consumed
            message = await receive()
            if message["type"] == "http.request":
                consumed += len(message.get("body", b""))
                if consumed > maximum:
                    # The crossing chunk is never forwarded to JSON/multipart parsing.
                    raise rejection("request_body_too_large", 413)
            return message

        await self.app(scope, bounded_receive, send)
