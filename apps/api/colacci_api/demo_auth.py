"""Allowlisted synthetic identities for test and demo profiles only."""

from __future__ import annotations

from fastapi import Header, HTTPException, Request, status

from packages.config import AppProfile
from packages.contracts.report import DemoPrincipal, DemoPrincipalId, DemoRole

PRINCIPALS = {
    DemoPrincipalId.REVIEWER: DemoRole.REVIEWER,
    DemoPrincipalId.ADMIN: DemoRole.ADMINISTRATOR,
    DemoPrincipalId.OPERATIONS: DemoRole.OPERATIONS,
}


def _detail(request: Request, error: str) -> dict[str, str]:
    return {
        "error": error,
        "correlation_id": str(getattr(request.state, "correlation_id", "correlation-unavailable")),
    }


def demo_principal(
    request: Request,
    x_demo_principal: str | None = Header(default=None, alias="X-Demo-Principal"),
) -> DemoPrincipal:
    settings = request.app.state.settings
    if settings.app_profile not in {AppProfile.TEST, AppProfile.DEMO}:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_detail(request, "not_found")
        )
    if x_demo_principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_detail(request, "select_an_allowlisted_demo_principal"),
        )
    try:
        principal_id = DemoPrincipalId(x_demo_principal)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_detail(request, "select_an_allowlisted_demo_principal"),
        ) from exc
    return DemoPrincipal(
        principal_id=principal_id,
        role=PRINCIPALS[principal_id],
        synthetic=True,
    )
