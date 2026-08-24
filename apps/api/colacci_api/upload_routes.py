"""Narrow authenticated API routes for one local synthetic upload at a time."""

from __future__ import annotations

from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from apps.api.colacci_api.demo_auth import demo_principal
from apps.api.colacci_api.errors import api_error
from packages.authorization import DemoPermission, has_permission
from packages.contracts.manual_upload import (
    UploadCapabilities,
    UploadList,
    UploadReceipt,
    UploadState,
)
from packages.contracts.report import DemoPrincipal
from packages.database.manual_uploads import (
    ManualUploadRepository,
    SubmissionConflictError,
    UploadStateConflictError,
)
from packages.database.review_experience import ReviewExperienceRepository
from packages.manual_upload.request_boundary import (
    MAX_MULTIPART_OVERHEAD,
    UploadRequestError,
    parse_audio_multipart,
    parse_header_metadata,
    require_bounded_content_length,
)
from packages.manual_upload.service import ManualUploadService, ManualUploadUnexpectedError
from packages.review.transcript_import import TRANSCRIPT_ONLY_MAX_BYTES

router = APIRouter(prefix="/api/uploads", tags=["synthetic-manual-upload"])
Principal = Annotated[DemoPrincipal, Depends(demo_principal)]


def _audit(
    request: Request,
    principal: DemoPrincipal,
    *,
    action: str,
    target_id: str,
    result: str,
) -> None:
    ReviewExperienceRepository(request.app.state.engine).record_audit(
        principal=principal,
        action=action,
        target_type="manual_upload",
        target_id=target_id,
        result=result,
    )


def _authorize(
    request: Request,
    principal: DemoPrincipal,
    *,
    action: str,
    target_id: str,
) -> None:
    if not has_permission(principal.role, DemoPermission.MANAGE_UPLOADS):
        _audit(
            request,
            principal,
            action=f"{action}_denied",
            target_id=target_id,
            result="forbidden",
        )
        raise api_error(
            request,
            status.HTTP_403_FORBIDDEN,
            "Only demo administrators and operations can use synthetic manual upload.",
        )
    _audit(
        request,
        principal,
        action=f"{action}_authorized",
        target_id=target_id,
        result="allowed",
    )


def _service(request: Request) -> ManualUploadService:
    return ManualUploadService(
        request.app.state.settings,
        request.app.state.engine,
        operational_logger=request.app.state.operational_logger,
        correlation_id=str(getattr(request.state, "correlation_id", "correlation-unavailable")),
    )


def _repository(request: Request) -> ManualUploadRepository:
    return ManualUploadRepository(request.app.state.engine)


def _audit_deletion_failure(
    request: Request, principal: DemoPrincipal, receipt: UploadReceipt
) -> None:
    if receipt.state is UploadState.DELETION_FAILED:
        _audit(
            request,
            principal,
            action="upload_deletion_failed",
            target_id=receipt.upload_id,
            result="failed",
        )


def _safe_upload_error(request: Request, exc: Exception) -> HTTPException:
    if isinstance(exc, UploadRequestError):
        return api_error(request, exc.status_code, exc.code)
    if isinstance(exc, SubmissionConflictError):
        return api_error(request, status.HTTP_409_CONFLICT, "submission_content_conflict")
    if isinstance(exc, UploadStateConflictError):
        return api_error(request, status.HTTP_409_CONFLICT, str(exc))
    if isinstance(exc, LookupError):
        return api_error(request, status.HTTP_404_NOT_FOUND, "upload_receipt_not_found")
    if isinstance(exc, ManualUploadUnexpectedError):
        return api_error(request, status.HTTP_500_INTERNAL_SERVER_ERROR, "manual_upload_failed")
    return api_error(request, status.HTTP_500_INTERNAL_SERVER_ERROR, "manual_upload_failed")


def _raise_safe_upload_error(request: Request, exc: Exception) -> NoReturn:
    if not isinstance(
        exc,
        UploadRequestError
        | SubmissionConflictError
        | UploadStateConflictError
        | LookupError
        | ManualUploadUnexpectedError,
    ):
        request.app.state.operational_logger.event(
            "manual_upload_request_failed",
            level="error",
            component="manual_upload",
            correlation_id=str(getattr(request.state, "correlation_id", "correlation-unavailable")),
            error_code="unexpected_manual_upload_failure",
            status="failed",
        )
    raise _safe_upload_error(request, exc) from exc


@router.get("/capabilities", response_model=UploadCapabilities)
def capabilities(principal: Principal) -> UploadCapabilities:
    can_upload = has_permission(principal.role, DemoPermission.MANAGE_UPLOADS)
    return UploadCapabilities(
        principal_id=principal.principal_id,
        role=principal.role,
        can_open_completed=has_permission(principal.role, DemoPermission.VIEW_REPORTS),
        can_append_feedback=has_permission(principal.role, DemoPermission.APPEND_FEEDBACK),
        can_submit=can_upload,
        can_view_receipts=can_upload,
        can_retry=can_upload,
        can_cancel=can_upload,
        can_publish_playbook=has_permission(principal.role, DemoPermission.MANAGE_PLAYBOOKS),
    )


@router.get("", response_model=UploadList)
def uploads(request: Request, principal: Principal) -> UploadList:
    _authorize(request, principal, action="upload_receipts_view", target_id="receipt-list")
    return UploadList(uploads=tuple(item.receipt for item in _repository(request).list()))


@router.get("/{upload_id}", response_model=UploadReceipt)
def upload(upload_id: str, request: Request, principal: Principal) -> UploadReceipt:
    _authorize(request, principal, action="upload_receipt_view", target_id=upload_id)
    stored = _repository(request).get(upload_id)
    if stored is None:
        raise api_error(request, status.HTTP_404_NOT_FOUND, "upload_receipt_not_found")
    return stored.receipt


@router.post("/audio", response_model=UploadReceipt, status_code=status.HTTP_201_CREATED)
async def submit_audio(
    request: Request,
    response: Response,
    principal: Principal,
) -> UploadReceipt:
    _authorize(request, principal, action="synthetic_audio_submit", target_id="new-receipt")
    settings = request.app.state.settings
    try:
        maximum = settings.media_max_bytes + MAX_MULTIPART_OVERHEAD
        require_bounded_content_length(request.headers.get("content-length"), maximum=maximum)
        body = await request.body()
        parsed = parse_audio_multipart(
            body,
            content_type=request.headers.get("content-type", ""),
            max_media_bytes=settings.media_max_bytes,
        )
        result = _service(request).submit_audio(parsed, principal=principal)
    except Exception as exc:
        _raise_safe_upload_error(request, exc)
    if result.duplicate:
        response.status_code = status.HTTP_200_OK
    return result.stored.receipt.model_copy(update={"duplicate": result.duplicate})


@router.post("/transcript", response_model=UploadReceipt, status_code=status.HTTP_201_CREATED)
async def submit_transcript(
    request: Request,
    response: Response,
    principal: Principal,
) -> UploadReceipt:
    _authorize(request, principal, action="transcript_submit", target_id="new-receipt")
    try:
        require_bounded_content_length(
            request.headers.get("content-length"), maximum=TRANSCRIPT_ONLY_MAX_BYTES
        )
        content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise UploadRequestError("transcript_content_type_required", status_code=415)
        metadata = parse_header_metadata(
            {key.lower(): value for key, value in request.headers.items()}
        )
        payload = await request.body()
        result = _service(request).submit_transcript(
            payload,
            metadata=metadata,
            principal=principal,
        )
    except Exception as exc:
        _raise_safe_upload_error(request, exc)
    if result.duplicate:
        response.status_code = status.HTTP_200_OK
    return result.stored.receipt.model_copy(update={"duplicate": result.duplicate})


@router.post("/{upload_id}/process", response_model=UploadReceipt)
def process(upload_id: str, request: Request, principal: Principal) -> UploadReceipt:
    _authorize(request, principal, action="upload_process", target_id=upload_id)
    try:
        receipt = _service(request).process_audio(upload_id).receipt
    except Exception as exc:
        _raise_safe_upload_error(request, exc)
    _audit_deletion_failure(request, principal, receipt)
    return receipt


@router.post("/{upload_id}/retry", response_model=UploadReceipt)
def retry(upload_id: str, request: Request, principal: Principal) -> UploadReceipt:
    _authorize(request, principal, action="upload_retry", target_id=upload_id)
    stored = _repository(request).get(upload_id)
    if stored is None:
        raise api_error(request, status.HTTP_404_NOT_FOUND, "upload_receipt_not_found")
    if not stored.receipt.retryable or stored.receipt.state not in {
        UploadState.TRANSCRIPTION_FAILED,
        UploadState.ANALYSIS_FAILED,
    }:
        raise api_error(request, status.HTTP_409_CONFLICT, "upload_failure_not_retryable")
    try:
        receipt = _service(request).process_audio(upload_id).receipt
    except Exception as exc:
        _raise_safe_upload_error(request, exc)
    _audit_deletion_failure(request, principal, receipt)
    return receipt


@router.delete("/{upload_id}", response_model=UploadReceipt)
def cancel(upload_id: str, request: Request, principal: Principal) -> UploadReceipt:
    _authorize(request, principal, action="upload_cancel", target_id=upload_id)
    try:
        receipt = _service(request).cancel(upload_id).receipt
    except Exception as exc:
        _raise_safe_upload_error(request, exc)
    _audit_deletion_failure(request, principal, receipt)
    return receipt
