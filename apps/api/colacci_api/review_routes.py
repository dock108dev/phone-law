"""Typed, authenticated, synthetic-only review experience routes."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from apps.api.colacci_api.demo_auth import demo_principal
from packages.contracts.report import (
    AuditEvent,
    CallDetail,
    DailyReport,
    DemoPrincipal,
    DemoRole,
    FailureQueue,
    MonthHistory,
    PlaybookActionResult,
    PlaybookDraftCreate,
    PlaybookDraftResult,
    PlaybookSummary,
    ReportDateList,
    RetryResult,
    ReviewEvent,
    ReviewEventCreate,
)
from packages.contracts.review import Finding, ProcessingState, Provenance, TranscriptSegment
from packages.database.repository import ReviewRepository
from packages.database.review_experience import ReviewExperienceRepository
from packages.review.fixtures import FixtureCallSource
from packages.review.pipeline import FixturePipeline

router = APIRouter(prefix="/api", tags=["synthetic-review"])
Principal = Annotated[DemoPrincipal, Depends(demo_principal)]


def _repository(request: Request) -> ReviewExperienceRepository:
    return ReviewExperienceRepository(request.app.state.engine)


def _error(request: Request, code: int, message: str) -> HTTPException:
    return HTTPException(
        status_code=code,
        detail={
            "error": message,
            "correlation_id": str(
                getattr(request.state, "correlation_id", "correlation-unavailable")
            ),
        },
    )


@router.get("/reports/dates", response_model=ReportDateList)
def report_dates(request: Request, _: Principal) -> ReportDateList:
    return ReportDateList(dates=_repository(request).report_dates())


@router.get("/reports/months/{year}-{month}", response_model=MonthHistory)
def month_history(year: int, month: int, request: Request, _: Principal) -> MonthHistory:
    if year < 2000 or year > 2100 or month < 1 or month > 12:
        raise _error(request, status.HTTP_404_NOT_FOUND, "synthetic_month_not_found")
    try:
        return _repository(request).month_history(year, month)
    except LookupError as exc:
        raise _error(request, status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("/reports/{business_date}", response_model=DailyReport)
def report(
    business_date: date,
    request: Request,
    _: Principal,
) -> DailyReport:
    result = _repository(request).report(business_date)
    if result is None:
        raise _error(request, status.HTTP_404_NOT_FOUND, "synthetic_report_not_found")
    return result


def _call(request: Request, call_id: str) -> CallDetail:
    result = _repository(request).call_detail(call_id)
    if result is None:
        raise _error(request, status.HTTP_404_NOT_FOUND, "synthetic_call_not_found")
    return result


@router.get("/calls/{call_id}", response_model=CallDetail)
def call_detail(
    call_id: str,
    request: Request,
    _: Principal,
) -> CallDetail:
    return _call(request, call_id)


@router.get("/calls/{call_id}/transcript", response_model=tuple[TranscriptSegment, ...])
def transcript_segments(
    call_id: str,
    request: Request,
    _: Principal,
) -> tuple[TranscriptSegment, ...]:
    return _call(request, call_id).transcript_segments


@router.get("/calls/{call_id}/findings", response_model=tuple[Finding, ...])
def findings(
    call_id: str,
    request: Request,
    _: Principal,
) -> tuple[Finding, ...]:
    return _call(request, call_id).findings


@router.get("/calls/{call_id}/provenance", response_model=Provenance)
def provenance(
    call_id: str,
    request: Request,
    _: Principal,
) -> Provenance:
    return _call(request, call_id).provenance


@router.get("/analyses/{analysis_id}/reviews", response_model=tuple[ReviewEvent, ...])
def review_history(
    analysis_id: str,
    request: Request,
    _: Principal,
) -> tuple[ReviewEvent, ...]:
    return _repository(request).review_history(analysis_id)


@router.post(
    "/analyses/{analysis_id}/reviews",
    response_model=ReviewEvent,
    status_code=status.HTTP_201_CREATED,
)
def create_review(
    analysis_id: str,
    payload: ReviewEventCreate,
    request: Request,
    principal: Principal,
) -> ReviewEvent:
    repository = _repository(request)
    if principal.role is DemoRole.OPERATIONS:
        repository.record_audit(
            principal=principal,
            action="review_event_create_denied",
            target_type="analysis",
            target_id=analysis_id,
            result="forbidden",
        )
        raise _error(
            request,
            status.HTTP_403_FORBIDDEN,
            "The operations role cannot record finding feedback.",
        )
    try:
        return repository.add_review(analysis_id=analysis_id, request=payload, principal=principal)
    except LookupError as exc:
        raise _error(request, status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("/failures", response_model=FailureQueue)
def failure_queue(
    request: Request,
    principal: Principal,
) -> FailureQueue:
    if principal.role not in {DemoRole.ADMINISTRATOR, DemoRole.OPERATIONS}:
        _repository(request).record_audit(
            principal=principal,
            action="failure_queue_view_denied",
            target_type="failure_queue",
            target_id="synthetic-failures",
            result="forbidden",
        )
        raise _error(
            request,
            status.HTTP_403_FORBIDDEN,
            "Only demo administrators and operations can view the failure queue.",
        )
    return _repository(request).failure_queue()


@router.post("/failures/{call_id}/retry", response_model=RetryResult)
def retry_failure(
    call_id: str,
    request: Request,
    principal: Principal,
) -> RetryResult:
    repository = _repository(request)
    if principal.role not in {DemoRole.ADMINISTRATOR, DemoRole.OPERATIONS}:
        repository.record_audit(
            principal=principal,
            action="synthetic_retry_denied",
            target_type="call",
            target_id=call_id,
            result="forbidden",
        )
        raise _error(
            request,
            status.HTTP_403_FORBIDDEN,
            "Only demo administrators and operations can retry a synthetic failure.",
        )
    target = repository.retry_target(call_id)
    if target is None:
        raise _error(request, status.HTTP_404_NOT_FOUND, "synthetic_failure_not_found")
    fixture_id, retryable, current_state = target
    if not retryable or current_state not in {
        ProcessingState.TRANSCRIPTION_FAILED,
        ProcessingState.ANALYSIS_FAILED,
    }:
        repository.record_audit(
            principal=principal,
            action="synthetic_retry_rejected",
            target_type="call",
            target_id=call_id,
            result="not_retryable",
        )
        raise _error(
            request,
            status.HTTP_409_CONFLICT,
            "This synthetic failure is permanent or already resolved and cannot be retried.",
        )
    source = FixtureCallSource()
    outcome = FixturePipeline(ReviewRepository(request.app.state.engine), source=source).retry(
        source.events(fixture_id)[0], call_id
    )
    repository.record_audit(
        principal=principal,
        action="synthetic_retry_completed",
        target_type="call",
        target_id=call_id,
        result=outcome.terminal_state.value.lower(),
    )
    return RetryResult(
        call_id=call_id,
        result="retry_completed",
        terminal_state=outcome.terminal_state,
        attempt_count=outcome.attempt_count,
    )


@router.get("/playbooks", response_model=tuple[PlaybookSummary, ...])
def playbooks(request: Request, _: Principal) -> tuple[PlaybookSummary, ...]:
    return _repository(request).playbooks()


@router.post("/playbooks/drafts", response_model=PlaybookDraftResult, status_code=201)
def create_playbook_draft(
    draft: PlaybookDraftCreate,
    request: Request,
    principal: Principal,
) -> PlaybookDraftResult:
    repository = _repository(request)
    if principal.role is not DemoRole.ADMINISTRATOR:
        repository.record_audit(
            principal=principal,
            action="playbook_draft_create_denied",
            target_type="playbook",
            target_id="synthetic-draft",
            result="forbidden",
        )
        raise _error(
            request,
            status.HTTP_403_FORBIDDEN,
            "Only the demo administrator can create a synthetic playbook draft.",
        )
    try:
        return repository.create_playbook_draft(request=draft, principal=principal)
    except LookupError as exc:
        raise _error(request, status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ValueError as exc:
        raise _error(request, status.HTTP_409_CONFLICT, str(exc)) from exc


@router.post("/playbooks/{version}/publish", response_model=PlaybookActionResult)
def publish_playbook(
    version: str,
    request: Request,
    principal: Principal,
) -> PlaybookActionResult:
    repository = _repository(request)
    if principal.role is not DemoRole.ADMINISTRATOR:
        repository.record_audit(
            principal=principal,
            action="playbook_publish_denied",
            target_type="playbook",
            target_id=version,
            result="forbidden",
        )
        raise _error(
            request,
            status.HTTP_403_FORBIDDEN,
            "Only the demo administrator can publish a synthetic playbook.",
        )
    try:
        return repository.publish_playbook(version=version, principal=principal)
    except LookupError as exc:
        raise _error(request, status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ValueError as exc:
        raise _error(request, status.HTTP_409_CONFLICT, str(exc)) from exc


@router.get("/audit-events", response_model=tuple[AuditEvent, ...])
def audit_history(
    request: Request,
    principal: Principal,
) -> tuple[AuditEvent, ...]:
    if principal.role not in {DemoRole.ADMINISTRATOR, DemoRole.OPERATIONS}:
        _repository(request).record_audit(
            principal=principal,
            action="audit_history_view_denied",
            target_type="audit_history",
            target_id="content-free-events",
            result="forbidden",
        )
        raise _error(
            request,
            status.HTTP_403_FORBIDDEN,
            "Only demo administrators and operations can view audit history.",
        )
    return _repository(request).audit_history()
