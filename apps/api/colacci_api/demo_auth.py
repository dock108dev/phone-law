"""Allowlisted synthetic identities for test and demo profiles only."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import Header, Request, status
from sqlalchemy.exc import SQLAlchemyError

from apps.api.colacci_api.errors import api_error
from packages.config import AppProfile
from packages.contracts.report import DemoPrincipal, DemoPrincipalId, DemoRole
from packages.database.review_schema import audit_events

PRINCIPALS = {
    DemoPrincipalId.REVIEWER: DemoRole.REVIEWER,
    DemoPrincipalId.ADMIN: DemoRole.ADMINISTRATOR,
    DemoPrincipalId.OPERATIONS: DemoRole.OPERATIONS,
}


def _audit_auth(request: Request, *, action: str, target_id: str, result: str) -> None:
    """Best-effort sanitized auth evidence without retaining caller input."""

    engine = getattr(request.app.state, "engine", None)
    if engine is None:
        return
    try:
        with engine.begin() as connection:
            connection.execute(
                audit_events.insert().values(
                    id=uuid4().hex,
                    principal_id=DemoPrincipalId.OPERATIONS.value,
                    role=DemoRole.OPERATIONS.value,
                    action=action,
                    target_type="demo_session",
                    target_id=target_id,
                    result=result,
                    created_at=datetime.now(UTC),
                )
            )
    except SQLAlchemyError:
        logger = getattr(request.app.state, "operational_logger", None)
        if logger is None:
            return
        logger.event(
            "authorization_audit_unavailable",
            level="warning",
            correlation_id=str(getattr(request.state, "correlation_id", "correlation-unavailable")),
            status="unavailable",
        )


def demo_principal(
    request: Request,
    x_demo_principal: str | None = Header(default=None, alias="X-Demo-Principal"),
    x_demo_session: str | None = Header(default=None, alias="X-Demo-Session"),
    x_demo_role: str | None = Header(default=None, alias="X-Demo-Role"),
) -> DemoPrincipal:
    if not isinstance(x_demo_session, str):
        x_demo_session = None
    if not isinstance(x_demo_role, str):
        x_demo_role = None
    settings = request.app.state.settings
    if settings.app_profile not in {AppProfile.TEST, AppProfile.DEMO}:
        raise api_error(request, status.HTTP_404_NOT_FOUND, "not_found")
    if x_demo_principal is None:
        _audit_auth(
            request,
            action="demo_identity_missing",
            target_id="anonymous-session",
            result="denied",
        )
        raise api_error(
            request,
            status.HTTP_401_UNAUTHORIZED,
            "select_an_allowlisted_demo_principal",
        )
    try:
        principal_id = DemoPrincipalId(x_demo_principal)
    except ValueError as exc:
        _audit_auth(
            request,
            action="demo_identity_invalid",
            target_id="invalid-session",
            result="denied",
        )
        raise api_error(
            request,
            status.HTTP_401_UNAUTHORIZED,
            "select_an_allowlisted_demo_principal",
        ) from exc
    if x_demo_session not in {None, "active"}:
        _audit_auth(
            request,
            action="demo_session_expired",
            target_id=principal_id.value,
            result="denied",
        )
        raise api_error(request, status.HTTP_401_UNAUTHORIZED, "demo_session_expired")
    resolved_role = PRINCIPALS[principal_id]
    if x_demo_role is not None:
        _audit_auth(
            request,
            action="caller_role_ignored",
            target_id=principal_id.value,
            result="server_role_applied",
        )
    return DemoPrincipal(
        principal_id=principal_id,
        role=resolved_role,
        synthetic=True,
    )
