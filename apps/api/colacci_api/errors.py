"""Authoritative sanitized API error envelope."""

from fastapi import HTTPException, Request


def api_error(request: Request, code: int, message: str) -> HTTPException:
    return HTTPException(
        status_code=code,
        detail={
            "error": message,
            "correlation_id": str(
                getattr(request.state, "correlation_id", "correlation-unavailable")
            ),
        },
    )
