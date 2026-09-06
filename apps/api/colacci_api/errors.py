"""Authoritative sanitized API error envelope for routes and middleware."""

from fastapi import HTTPException, Request
from starlette.responses import JSONResponse


def error_detail(message: str, correlation_id: object) -> dict[str, str]:
    return {"error": message, "correlation_id": str(correlation_id)}


def error_response(code: int, message: str, correlation_id: object) -> JSONResponse:
    return JSONResponse(status_code=code, content={"detail": error_detail(message, correlation_id)})


def api_error(request: Request, code: int, message: str) -> HTTPException:
    return HTTPException(
        status_code=code,
        detail=error_detail(
            message, getattr(request.state, "correlation_id", "correlation-unavailable")
        ),
    )
