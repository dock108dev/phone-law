"""Authorized, content-free local operations routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from apps.api.colacci_api.demo_auth import demo_principal
from apps.api.colacci_api.errors import api_error
from packages.authorization import DemoPermission, has_permission
from packages.contracts.operations import (
    BackupRestoreDrillResult,
    ConfigurationHistory,
    ConfigurationVersion,
    DeletionJob,
    LocalFirmConfiguration,
    NotificationPreview,
    OperationsOverview,
    RetentionRunResult,
)
from packages.contracts.report import DemoPrincipal
from packages.database.local_operations import LocalOperationsRepository
from packages.database.review_experience import ReviewExperienceRepository

router = APIRouter(prefix="/api/operations", tags=["local-operations"])
Principal = Annotated[DemoPrincipal, Depends(demo_principal)]


def _repository(request: Request) -> LocalOperationsRepository:
    return LocalOperationsRepository(
        request.app.state.engine,
        request.app.state.settings,
    )


def _authorize(
    request: Request,
    principal: DemoPrincipal,
    *,
    action: str,
    administrator_only: bool = False,
) -> None:
    permission = (
        DemoPermission.PUBLISH_CONFIGURATION
        if administrator_only
        else DemoPermission.USE_OPERATIONS
    )
    allowed = has_permission(principal.role, permission)
    ReviewExperienceRepository(request.app.state.engine).record_audit(
        principal=principal,
        action=f"{action}_{'authorized' if allowed else 'denied'}",
        target_type="local_operations",
        target_id="operations-center",
        result="allowed" if allowed else "forbidden",
    )
    if not allowed:
        raise api_error(request, status.HTTP_403_FORBIDDEN, "local_operations_access_denied")


@router.get("/overview", response_model=OperationsOverview)
def overview(request: Request, principal: Principal) -> OperationsOverview:
    _authorize(request, principal, action="operations_overview_view")
    return _repository(request).operations_overview(principal=principal)


@router.get("/configuration", response_model=ConfigurationHistory)
def configuration_history(request: Request, principal: Principal) -> ConfigurationHistory:
    _authorize(request, principal, action="configuration_history_view")
    return _repository(request).configuration_history()


@router.post(
    "/configuration",
    response_model=ConfigurationVersion,
    status_code=status.HTTP_201_CREATED,
)
def publish_configuration(
    payload: LocalFirmConfiguration,
    request: Request,
    principal: Principal,
) -> ConfigurationVersion:
    _authorize(
        request,
        principal,
        action="configuration_publish",
        administrator_only=True,
    )
    try:
        return _repository(request).publish_configuration(payload, principal=principal)
    except ValueError as exc:
        raise api_error(request, status.HTTP_409_CONFLICT, str(exc)) from exc


@router.post("/retention/run", response_model=RetentionRunResult)
def run_retention(request: Request, principal: Principal) -> RetentionRunResult:
    _authorize(request, principal, action="retention_run")
    return _repository(request).run_retention(principal=principal)


@router.get("/deletions", response_model=tuple[DeletionJob, ...])
def deletion_jobs(request: Request, principal: Principal) -> tuple[DeletionJob, ...]:
    _authorize(request, principal, action="deletion_jobs_view")
    return _repository(request).deletion_jobs()


@router.post("/deletions/{job_id}/retry", response_model=DeletionJob)
def retry_deletion(job_id: str, request: Request, principal: Principal) -> DeletionJob:
    _authorize(request, principal, action="deletion_retry")
    try:
        return _repository(request).retry_deletion(job_id, principal=principal)
    except LookupError as exc:
        raise api_error(request, status.HTTP_404_NOT_FOUND, "deletion_job_not_found") from exc
    except ValueError as exc:
        raise api_error(request, status.HTTP_409_CONFLICT, str(exc)) from exc


@router.post("/backup-restore-drill", response_model=BackupRestoreDrillResult)
def backup_restore_drill(request: Request, principal: Principal) -> BackupRestoreDrillResult:
    _authorize(request, principal, action="backup_restore_drill")
    return _repository(request).run_backup_restore_drill(principal=principal)


@router.post("/notification-preview", response_model=NotificationPreview)
def notification_preview(request: Request, principal: Principal) -> NotificationPreview:
    _authorize(request, principal, action="notification_preview")
    overview_result = _repository(request).operations_overview(principal=principal)
    return _repository(request).notification_preview(
        principal=principal,
        safe_count=overview_result.pending_deletions + overview_result.failed_deletions,
        internal_reference="operations-center",
    )
