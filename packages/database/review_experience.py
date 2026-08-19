"""Persistence boundary for immutable reports, feedback, failures, and playbooks."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from typing import cast
from uuid import uuid4
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from pydantic import BaseModel
from sqlalchemy import Engine

from packages.contracts.report import (
    AuditEvent,
    CallDetail,
    DailyReport,
    DemoPrincipal,
    DemoPrincipalId,
    DemoRole,
    FailedCallSummary,
    FailureQueue,
    FailureQueueItem,
    PlaybookActionResult,
    PlaybookLifecycleState,
    PlaybookSummary,
    ProcessingAttemptSummary,
    ReviewEvent,
    ReviewEventCreate,
    ReviewLabel,
)
from packages.contracts.review import (
    Finding,
    NormalizedCall,
    PlaybookVersion,
    ProcessingState,
    StructuredAnalysis,
    Transcript,
)
from packages.database.review_schema import (
    analyses,
    audit_events,
    calls,
    daily_report_items,
    daily_reports,
    ingestion_events,
    playbook_versions,
    processing_attempts,
    retention_tombstones,
    review_events,
    transcripts,
)
from packages.review.reporting import ReportCallInput, aggregate_daily_report


def _id() -> str:
    return uuid4().hex


def _validated[ModelT: BaseModel](model: type[ModelT], payload: object) -> ModelT:
    return model.model_validate_json(json.dumps(payload, ensure_ascii=False))


def _attempt_summary(row: sa.RowMapping) -> ProcessingAttemptSummary:
    return ProcessingAttemptSummary(
        attempt_id=str(row["id"]),
        attempt_number=int(row["attempt_number"]),
        state=ProcessingState(str(row["state"])),
        diagnostic_code=cast(str | None, row["diagnostic_code"]),
        retryable=cast(bool | None, row["retryable"]),
        started_at=cast(datetime, row["started_at"]),
        completed_at=cast(datetime | None, row["completed_at"]),
    )


def _failed_stage(state: ProcessingState) -> str:
    return {
        ProcessingState.AUDIO_INVALID: "media validation",
        ProcessingState.TRANSCRIPTION_FAILED: "transcription",
        ProcessingState.OUTPUT_VALIDATION_FAILED: "structured output validation",
        ProcessingState.ANALYSIS_FAILED: "analysis",
    }.get(state, "processing")


class ReviewExperienceRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def generate_report(
        self,
        *,
        business_date: date,
        cutoff_at: datetime,
        expected_source_call_ids: tuple[str, ...],
    ) -> DailyReport:
        timezone = ZoneInfo("America/New_York")
        with self.engine.connect() as connection:
            first_received = (
                sa.select(
                    ingestion_events.c.call_id,
                    sa.func.min(ingestion_events.c.received_at).label("received_at"),
                )
                .group_by(ingestion_events.c.call_id)
                .subquery()
            )
            call_rows = (
                connection.execute(
                    sa.select(
                        calls,
                        analyses.c.original_payload.label("analysis_payload"),
                        first_received.c.received_at,
                    )
                    .join(first_received, first_received.c.call_id == calls.c.id)
                    .outerjoin(analyses, analyses.c.call_id == calls.c.id)
                    .where(calls.c.is_synthetic.is_(True))
                )
                .mappings()
                .all()
            )
            report_calls: list[ReportCallInput] = []
            fingerprint_rows: list[dict[str, object]] = []
            for row in call_rows:
                occurred_at = cast(datetime, row["occurred_at"])
                if occurred_at.astimezone(timezone).date() != business_date:
                    continue
                state = ProcessingState(str(row["state"]))
                analysis_payload = row["analysis_payload"]
                analysis = (
                    _validated(StructuredAnalysis, analysis_payload)
                    if analysis_payload is not None
                    else None
                )
                failure: FailedCallSummary | None = None
                if analysis is None and state in {
                    ProcessingState.AUDIO_INVALID,
                    ProcessingState.TRANSCRIPTION_FAILED,
                    ProcessingState.OUTPUT_VALIDATION_FAILED,
                    ProcessingState.ANALYSIS_FAILED,
                }:
                    attempt = (
                        connection.execute(
                            sa.select(processing_attempts)
                            .where(processing_attempts.c.call_id == row["id"])
                            .order_by(processing_attempts.c.attempt_number.desc())
                            .limit(1)
                        )
                        .mappings()
                        .one()
                    )
                    failure = FailedCallSummary(
                        call_id=str(row["id"]),
                        synthetic_reference=str(row["fixture_id"]),
                        failed_stage=_failed_stage(state),
                        diagnostic_code=str(attempt["diagnostic_code"]),
                        retryable=bool(attempt["retryable"]),
                        terminal_state=state,
                    )
                report_calls.append(
                    ReportCallInput(
                        call_id=str(row["id"]),
                        synthetic_reference=str(row["fixture_id"]),
                        source_call_id=str(row["source_call_id"]),
                        occurred_at=occurred_at,
                        received_at=cast(datetime, row["received_at"]),
                        state=state,
                        analysis=analysis,
                        failure=failure,
                    )
                )
                fingerprint_rows.append(
                    {
                        "source_call_id": row["source_call_id"],
                        "state": state.value,
                        "analysis": analysis_payload,
                        "failure": failure.model_dump(mode="json") if failure else None,
                    }
                )
            report_call_ids = tuple(item.call_id for item in report_calls)
            event_rows = (
                connection.execute(
                    sa.select(
                        ingestion_events.c.disposition,
                        ingestion_events.c.duplicate_delivery_count,
                    ).where(ingestion_events.c.call_id.in_(report_call_ids))
                )
                .mappings()
                .all()
                if report_call_ids
                else []
            )
            duplicates = sum(
                int(row["duplicate_delivery_count"])
                + (1 if row["disposition"] == "duplicate_call" else 0)
                for row in event_rows
            )
            fingerprint_payload = {
                "business_date": str(business_date),
                "cutoff_at": cutoff_at.isoformat(),
                "expected": sorted(expected_source_call_ids),
                "duplicates": duplicates,
                "calls": sorted(fingerprint_rows, key=lambda item: str(item["source_call_id"])),
            }
            fingerprint = hashlib.sha256(
                json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            existing = connection.execute(
                sa.select(daily_reports.c.snapshot_payload).where(
                    daily_reports.c.business_date == business_date,
                    daily_reports.c.input_fingerprint == fingerprint,
                    ~sa.exists(
                        sa.select(retention_tombstones.c.id).where(
                            retention_tombstones.c.resource_type == "daily_report",
                            retention_tombstones.c.resource_id == daily_reports.c.id,
                        )
                    ),
                )
            ).scalar_one_or_none()
            if existing is not None:
                return _validated(DailyReport, existing)
            version = (
                int(
                    connection.execute(
                        sa.select(sa.func.coalesce(sa.func.max(daily_reports.c.version), 0)).where(
                            daily_reports.c.business_date == business_date
                        )
                    ).scalar_one()
                )
                + 1
            )

        report = aggregate_daily_report(
            business_date=business_date,
            cutoff_at=cutoff_at,
            expected_source_call_ids=expected_source_call_ids,
            calls=tuple(report_calls),
            duplicate_deliveries=duplicates,
            version=version,
            fingerprint=fingerprint,
        )
        with self.engine.begin() as connection:
            connection.execute(
                daily_reports.insert().values(
                    id=report.report_id,
                    business_date=business_date,
                    version=version,
                    status=report.completeness.status.value,
                    input_fingerprint=fingerprint,
                    cutoff_at=cutoff_at,
                    snapshot_payload=report.model_dump(mode="json"),
                    generated_at=report.generated_at,
                )
            )
            for section in report.sections:
                for position, item in enumerate(section.items):
                    persisted_id = hashlib.sha256(
                        f"{report.report_id}|{item.item_id}".encode()
                    ).hexdigest()[:32]
                    connection.execute(
                        daily_report_items.insert().values(
                            id=persisted_id,
                            report_id=report.report_id,
                            call_id=item.call_id,
                            analysis_id=item.analysis_id,
                            section=section.kind.value,
                            position=position,
                            item_payload=item.model_dump(mode="json"),
                        )
                    )
        return report

    def report_dates(self) -> tuple[date, ...]:
        with self.engine.connect() as connection:
            values = (
                connection.execute(
                    sa.select(daily_reports.c.business_date)
                    .where(
                        ~sa.exists(
                            sa.select(retention_tombstones.c.id).where(
                                retention_tombstones.c.resource_type == "daily_report",
                                retention_tombstones.c.resource_id == daily_reports.c.id,
                            )
                        )
                    )
                    .distinct()
                    .order_by(daily_reports.c.business_date.desc())
                )
                .scalars()
                .all()
            )
        return tuple(cast(date, item) for item in values)

    def expected_source_call_ids(self, business_date: date) -> tuple[str, ...]:
        timezone = ZoneInfo("America/New_York")
        with self.engine.connect() as connection:
            rows = connection.execute(
                sa.select(calls.c.source_call_id, calls.c.occurred_at).where(
                    calls.c.is_synthetic.is_(True)
                )
            ).all()
        return tuple(
            sorted(
                str(row.source_call_id)
                for row in rows
                if cast(datetime, row.occurred_at).astimezone(timezone).date() == business_date
            )
        )

    def report(self, business_date: date) -> DailyReport | None:
        with self.engine.connect() as connection:
            payload = connection.execute(
                sa.select(daily_reports.c.snapshot_payload)
                .where(
                    daily_reports.c.business_date == business_date,
                    ~sa.exists(
                        sa.select(retention_tombstones.c.id).where(
                            retention_tombstones.c.resource_type == "daily_report",
                            retention_tombstones.c.resource_id == daily_reports.c.id,
                        )
                    ),
                )
                .order_by(daily_reports.c.version.desc())
                .limit(1)
            ).scalar_one_or_none()
        return _validated(DailyReport, payload) if payload else None

    def review_history(self, analysis_id: str) -> tuple[ReviewEvent, ...]:
        with self.engine.connect() as connection:
            rows = (
                connection.execute(
                    sa.select(review_events)
                    .where(review_events.c.analysis_id == analysis_id)
                    .where(
                        ~sa.exists(
                            sa.select(retention_tombstones.c.id).where(
                                retention_tombstones.c.resource_type == "reviewer_feedback",
                                retention_tombstones.c.resource_id == review_events.c.id,
                            )
                        )
                    )
                    .order_by(review_events.c.created_at, review_events.c.id)
                )
                .mappings()
                .all()
            )
        return tuple(
            ReviewEvent(
                schema_version="review-event-v1",
                event_id=str(row["id"]),
                analysis_id=str(row["analysis_id"]),
                finding_id=cast(str | None, row["finding_id"]),
                label=ReviewLabel(str(row["label"])),
                note=cast(str | None, row["note"]),
                principal=DemoPrincipal(
                    principal_id=DemoPrincipalId(str(row["principal_id"])),
                    role=DemoRole(str(row["role"])),
                    synthetic=True,
                ),
                created_at=cast(datetime, row["created_at"]),
            )
            for row in rows
        )

    def call_detail(self, call_id: str) -> CallDetail | None:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    sa.select(
                        calls,
                        transcripts.c.original_payload.label("transcript_payload"),
                        analyses.c.original_payload.label("analysis_payload"),
                    )
                    .join(transcripts, transcripts.c.call_id == calls.c.id)
                    .join(analyses, analyses.c.call_id == calls.c.id)
                    .where(
                        calls.c.id == call_id,
                        calls.c.is_synthetic.is_(True),
                        ~sa.exists(
                            sa.select(retention_tombstones.c.id).where(
                                retention_tombstones.c.resource_type == "invented_transcript",
                                retention_tombstones.c.resource_id == transcripts.c.id,
                            )
                        ),
                        ~sa.exists(
                            sa.select(retention_tombstones.c.id).where(
                                retention_tombstones.c.resource_type == "accepted_analysis",
                                retention_tombstones.c.resource_id == analyses.c.id,
                            )
                        ),
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            attempt_rows = (
                connection.execute(
                    sa.select(processing_attempts)
                    .where(processing_attempts.c.call_id == call_id)
                    .order_by(processing_attempts.c.attempt_number)
                )
                .mappings()
                .all()
            )
        normalized = _validated(NormalizedCall, row["normalized_payload"])
        transcript = _validated(Transcript, row["transcript_payload"])
        analysis = _validated(StructuredAnalysis, row["analysis_payload"])
        finding_map: dict[str, Finding] = {}
        for finding in (
            *analysis.attorney_attention_issues,
            *analysis.dissatisfaction_indicators,
            *analysis.omitted_information_findings,
            *analysis.findings,
        ):
            finding_map.setdefault(finding.finding_id, finding)
        uncertainty = tuple(
            dict.fromkeys(
                (
                    *analysis.facts.missing_context,
                    *(item.question for item in analysis.facts.unresolved_questions),
                )
            )
        )
        return CallDetail(
            call_id=str(row["id"]),
            synthetic_reference=str(row["fixture_id"]),
            synthetic=True,
            occurred_at=cast(datetime, row["occurred_at"]),
            direction=normalized.direction,
            duration_seconds=normalized.duration_seconds,
            staff_extension=normalized.staff_extension,
            language=transcript.language,
            identity_state=analysis.facts.caller_identity.state.value,
            identity_label=analysis.facts.caller_identity.label,
            transcript_id=transcript.transcript_id,
            transcript_segments=transcript.segments,
            analysis_id=analysis.analysis_id,
            summary=analysis.summary,
            category=analysis.category,
            priority=analysis.priority.value,
            confidence=analysis.confidence,
            uncertainty=uncertainty,
            facts=analysis.facts,
            findings=tuple(finding_map.values()),
            proposed_next_steps=analysis.proposed_next_steps,
            responsible_role=analysis.responsible_role,
            suggested_response_timing=analysis.suggested_response_timing,
            provenance=analysis.provenance,
            attempts=tuple(_attempt_summary(item) for item in attempt_rows),
            review_history=self.review_history(analysis.analysis_id),
        )

    def add_review(
        self,
        *,
        analysis_id: str,
        request: ReviewEventCreate,
        principal: DemoPrincipal,
    ) -> ReviewEvent:
        now = datetime.now(UTC)
        event = ReviewEvent(
            schema_version="review-event-v1",
            event_id=_id(),
            analysis_id=analysis_id,
            finding_id=request.finding_id,
            label=request.label,
            note=request.note,
            principal=principal,
            created_at=now,
        )
        with self.engine.begin() as connection:
            payload = connection.execute(
                sa.select(analyses.c.original_payload).where(analyses.c.id == analysis_id)
            ).scalar_one_or_none()
            if payload is None:
                raise LookupError("analysis_not_found")
            analysis = _validated(StructuredAnalysis, payload)
            findings = {
                item.finding_id
                for item in (
                    *analysis.attorney_attention_issues,
                    *analysis.dissatisfaction_indicators,
                    *analysis.omitted_information_findings,
                    *analysis.findings,
                )
            }
            if request.finding_id is not None and request.finding_id not in findings:
                raise LookupError("finding_not_found")
            connection.execute(
                review_events.insert().values(
                    id=event.event_id,
                    analysis_id=analysis_id,
                    finding_id=event.finding_id,
                    label=event.label.value,
                    note=event.note,
                    principal_id=principal.principal_id.value,
                    role=principal.role.value,
                    created_at=now,
                )
            )
            self._insert_audit(
                connection,
                principal=principal,
                action="review_event_created",
                target_type="analysis",
                target_id=analysis_id,
                result="created",
                created_at=now,
            )
        return event

    def _insert_audit(
        self,
        connection: sa.Connection,
        *,
        principal: DemoPrincipal,
        action: str,
        target_type: str,
        target_id: str,
        result: str,
        created_at: datetime,
    ) -> AuditEvent:
        event = AuditEvent(
            schema_version="audit-event-v1",
            event_id=_id(),
            principal=principal,
            action=action,
            target_type=target_type,
            target_id=target_id,
            result=result,
            created_at=created_at,
        )
        connection.execute(
            audit_events.insert().values(
                id=event.event_id,
                principal_id=principal.principal_id.value,
                role=principal.role.value,
                action=event.action,
                target_type=event.target_type,
                target_id=event.target_id,
                result=event.result,
                created_at=created_at,
            )
        )
        return event

    def record_audit(
        self,
        *,
        principal: DemoPrincipal,
        action: str,
        target_type: str,
        target_id: str,
        result: str,
    ) -> AuditEvent:
        with self.engine.begin() as connection:
            return self._insert_audit(
                connection,
                principal=principal,
                action=action,
                target_type=target_type,
                target_id=target_id,
                result=result,
                created_at=datetime.now(UTC),
            )

    def audit_history(self) -> tuple[AuditEvent, ...]:
        with self.engine.connect() as connection:
            rows = (
                connection.execute(
                    sa.select(audit_events).order_by(audit_events.c.created_at, audit_events.c.id)
                )
                .mappings()
                .all()
            )
        return tuple(
            AuditEvent(
                schema_version="audit-event-v1",
                event_id=str(row["id"]),
                principal=DemoPrincipal(
                    principal_id=DemoPrincipalId(str(row["principal_id"])),
                    role=DemoRole(str(row["role"])),
                    synthetic=True,
                ),
                action=str(row["action"]),
                target_type=str(row["target_type"]),
                target_id=str(row["target_id"]),
                result=str(row["result"]),
                created_at=cast(datetime, row["created_at"]),
            )
            for row in rows
        )

    def failure_queue(self) -> FailureQueue:
        failure_states = {
            ProcessingState.AUDIO_INVALID.value,
            ProcessingState.TRANSCRIPTION_FAILED.value,
            ProcessingState.OUTPUT_VALIDATION_FAILED.value,
            ProcessingState.ANALYSIS_FAILED.value,
        }
        with self.engine.connect() as connection:
            call_rows = (
                connection.execute(sa.select(calls).where(calls.c.is_synthetic.is_(True)))
                .mappings()
                .all()
            )
            items: list[FailureQueueItem] = []
            for call in call_rows:
                attempts = (
                    connection.execute(
                        sa.select(processing_attempts)
                        .where(processing_attempts.c.call_id == call["id"])
                        .order_by(processing_attempts.c.attempt_number)
                    )
                    .mappings()
                    .all()
                )
                failures = [row for row in attempts if row["state"] in failure_states]
                if not failures:
                    continue
                latest_failure = failures[-1]
                current_state = ProcessingState(str(call["state"]))
                items.append(
                    FailureQueueItem(
                        call_id=str(call["id"]),
                        synthetic_reference=str(call["fixture_id"]),
                        failed_stage=_failed_stage(ProcessingState(str(latest_failure["state"]))),
                        diagnostic_code=str(latest_failure["diagnostic_code"]),
                        retryable=bool(latest_failure["retryable"]),
                        first_attempt_at=cast(datetime, attempts[0]["started_at"]),
                        latest_attempt_at=cast(datetime, attempts[-1]["started_at"]),
                        attempt_count=len(attempts),
                        current_terminal_state=current_state,
                        resolved=current_state is ProcessingState.ANALYZED,
                        attempt_history=tuple(_attempt_summary(row) for row in attempts),
                    )
                )
        ordered = sorted(items, key=lambda item: (item.synthetic_reference, item.call_id))
        return FailureQueue(
            current=tuple(item for item in ordered if not item.resolved),
            resolved=tuple(item for item in ordered if item.resolved),
        )

    def playbooks(self) -> tuple[PlaybookSummary, ...]:
        with self.engine.connect() as connection:
            rows = (
                connection.execute(
                    sa.select(playbook_versions)
                    .where(
                        ~sa.exists(
                            sa.select(retention_tombstones.c.id).where(
                                retention_tombstones.c.resource_type == "playbook_version",
                                retention_tombstones.c.resource_id == playbook_versions.c.id,
                            )
                        )
                    )
                    .order_by(playbook_versions.c.created_at)
                )
                .mappings()
                .all()
            )
        return tuple(self._playbook_summary(row) for row in rows)

    def _playbook_summary(self, row: sa.RowMapping | dict[str, object]) -> PlaybookSummary:
        playbook = _validated(PlaybookVersion, row["structured_payload"])
        key_rules = (
            *playbook.priority_rules,
            *playbook.evidence_requirements,
            *playbook.commitment_handling,
            *playbook.date_uncertainty_rules,
            *playbook.prompt_injection_boundary,
        )
        return PlaybookSummary(
            playbook_id=str(row["id"]),
            version=str(row["version"]),
            label=playbook.label,
            synthetic=True,
            lifecycle=PlaybookLifecycleState(str(row["status"])),
            categories=tuple(rule.outcome for rule in playbook.category_definitions),
            key_rules=tuple(rule.description for rule in key_rules),
            created_at=cast(datetime, row["created_at"]),
            published_at=cast(datetime | None, row["published_at"]),
        )

    def publish_playbook(self, *, version: str, principal: DemoPrincipal) -> PlaybookActionResult:
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(playbook_versions)
                    .where(playbook_versions.c.version == version)
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise LookupError("playbook_not_found")
            if row["status"] != PlaybookLifecycleState.DRAFT.value:
                raise ValueError("playbook_not_draft")
            connection.execute(
                playbook_versions.update()
                .where(playbook_versions.c.version == version)
                .values(status=PlaybookLifecycleState.PUBLISHED.value, published_at=now)
            )
            self._insert_audit(
                connection,
                principal=principal,
                action="playbook_published",
                target_type="playbook",
                target_id=str(row["id"]),
                result="published",
                created_at=now,
            )
            updated = dict(row)
            updated["status"] = PlaybookLifecycleState.PUBLISHED.value
            updated["published_at"] = now
        return PlaybookActionResult(playbook=self._playbook_summary(updated), result="published")

    def retry_target(self, call_id: str) -> tuple[str, bool, ProcessingState] | None:
        with self.engine.connect() as connection:
            row = connection.execute(
                sa.select(calls.c.fixture_id, calls.c.state).where(
                    calls.c.id == call_id, calls.c.is_synthetic.is_(True)
                )
            ).one_or_none()
            retryable = connection.execute(
                sa.select(processing_attempts.c.retryable)
                .where(processing_attempts.c.call_id == call_id)
                .order_by(processing_attempts.c.attempt_number.desc())
                .limit(1)
            ).scalar_one_or_none()
        if row is None:
            return None
        return str(row.fixture_id), bool(retryable), ProcessingState(str(row.state))
