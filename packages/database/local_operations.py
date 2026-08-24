"""Persistence and execution boundary for local-only operations."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol, cast
from uuid import uuid4

import sqlalchemy as sa
from pydantic import BaseModel
from sqlalchemy import Engine
from sqlalchemy.dialects.postgresql import insert

from packages.authorization import DemoPermission, has_permission, operations_actions
from packages.config import Settings
from packages.contracts.media import TemporaryObjectReference
from packages.contracts.operations import (
    BackupRestoreDrillResult,
    ConfigurationHistory,
    ConfigurationVersion,
    DeletionJob,
    DeletionState,
    LocalFirmConfiguration,
    MaintenanceKind,
    NotificationPreview,
    OperationsOverview,
    ReconciliationMetrics,
    RetentionResource,
    RetentionRunResult,
    SafeLatencyMetrics,
    SafeStateCount,
)
from packages.contracts.report import DemoPrincipal, DemoPrincipalId, DemoRole
from packages.database.review_schema import (
    analyses,
    audit_events,
    backup_restore_drills,
    calls,
    daily_report_items,
    daily_reports,
    firm_configuration_versions,
    maintenance_runs,
    manual_upload_receipts,
    media_artifacts,
    media_lifecycle_events,
    notification_previews,
    playbook_versions,
    processing_attempts,
    retention_jobs,
    retention_tombstones,
    review_events,
    transcription_provider_attempts,
    transcripts,
)
from packages.media.store import LocalSyntheticObjectStore

MAX_DELETION_ATTEMPTS = 3


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class DeletionFailurePlan(Protocol):
    def diagnostic_for(self, job: DeletionJob) -> str | None: ...


class NoDeletionFailures:
    def diagnostic_for(self, job: DeletionJob) -> str | None:
        return None


class ScriptedDeletionFailures:
    """Deterministic test-only deletion outcomes keyed by safe resource identifier."""

    def __init__(self, outcomes: Mapping[str, tuple[str | None, ...]]) -> None:
        self.outcomes = outcomes

    def diagnostic_for(self, job: DeletionJob) -> str | None:
        values = self.outcomes.get(job.resource_id, ())
        index = job.attempt_count
        return values[index] if index < len(values) else None


def _id() -> str:
    return uuid4().hex


def _json_payload(model: BaseModel) -> tuple[str, str]:
    serialized = json.dumps(model.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return serialized, hashlib.sha256(serialized.encode()).hexdigest()


def _audit(
    connection: sa.Connection,
    *,
    principal: DemoPrincipal,
    action: str,
    target_type: str,
    target_id: str,
    result: str,
    created_at: datetime,
) -> None:
    connection.execute(
        audit_events.insert().values(
            id=_id(),
            principal_id=principal.principal_id.value,
            role=principal.role.value,
            action=action,
            target_type=target_type,
            target_id=target_id,
            result=result,
            created_at=created_at,
        )
    )


class LocalOperationsRepository:
    def __init__(
        self,
        engine: Engine,
        settings: Settings,
        *,
        clock: Clock | None = None,
        failure_plan: DeletionFailurePlan | None = None,
    ) -> None:
        if not settings.synthetic_mode or settings.notification_adapter != "noop":
            raise ValueError("local_operations_boundary_rejected")
        self.engine = engine
        self.settings = settings
        self.clock = clock or SystemClock()
        self.failure_plan = failure_plan or NoDeletionFailures()

    def configuration_history(self) -> ConfigurationHistory:
        with self.engine.connect() as connection:
            rows = (
                connection.execute(
                    sa.select(firm_configuration_versions).order_by(
                        firm_configuration_versions.c.version.desc()
                    )
                )
                .mappings()
                .all()
            )
        versions = tuple(self._configuration_version(row) for row in rows)
        if not versions:
            raise RuntimeError("local_configuration_unavailable")
        return ConfigurationHistory(current_version=versions[0].version, versions=versions)

    def current_configuration(self) -> ConfigurationVersion:
        return self.configuration_history().versions[0]

    @staticmethod
    def _configuration_version(row: sa.RowMapping) -> ConfigurationVersion:
        configuration = LocalFirmConfiguration.model_validate_json(
            json.dumps(row["configuration_payload"], ensure_ascii=False)
        )
        return ConfigurationVersion(
            configuration_id=str(row["id"]),
            version=int(row["version"]),
            configuration=configuration,
            principal=DemoPrincipal(
                principal_id=DemoPrincipalId(str(row["principal_id"])),
                role=DemoRole(str(row["role"])),
                synthetic=True,
            ),
            content_hash_reference=f"sha256:{str(row['content_hash'])[:12]}",
            created_at=cast(datetime, row["created_at"]),
        )

    def publish_configuration(
        self, configuration: LocalFirmConfiguration, *, principal: DemoPrincipal
    ) -> ConfigurationVersion:
        if not has_permission(principal.role, DemoPermission.PUBLISH_CONFIGURATION):
            raise PermissionError("configuration_publish_forbidden")
        serialized, content_hash = _json_payload(configuration)
        now = self.clock.now()
        with self.engine.begin() as connection:
            latest = (
                connection.execute(
                    sa.select(firm_configuration_versions)
                    .order_by(firm_configuration_versions.c.version.desc())
                    .limit(1)
                    .with_for_update()
                )
                .mappings()
                .one()
            )
            if str(latest["content_hash"]) == content_hash:
                _audit(
                    connection,
                    principal=principal,
                    action="configuration_publish_rejected",
                    target_type="configuration",
                    target_id=str(latest["id"]),
                    result="unchanged",
                    created_at=now,
                )
                raise ValueError("configuration_unchanged")
            configuration_id = hashlib.sha256(
                f"{int(latest['version']) + 1}:{content_hash}".encode()
            ).hexdigest()[:32]
            version = int(latest["version"]) + 1
            connection.execute(
                firm_configuration_versions.insert().values(
                    id=configuration_id,
                    version=version,
                    schema_version=configuration.schema_version,
                    configuration_payload=json.loads(serialized),
                    content_hash=content_hash,
                    principal_id=principal.principal_id.value,
                    role=principal.role.value,
                    created_at=now,
                )
            )
            _audit(
                connection,
                principal=principal,
                action="configuration_published",
                target_type="configuration",
                target_id=configuration_id,
                result="published",
                created_at=now,
            )
            row = (
                connection.execute(
                    sa.select(firm_configuration_versions).where(
                        firm_configuration_versions.c.id == configuration_id
                    )
                )
                .mappings()
                .one()
            )
        return self._configuration_version(row)

    @staticmethod
    def _inventory_queries() -> dict[RetentionResource, tuple[sa.Table, sa.Column[object]]]:
        return {
            RetentionResource.GENERATED_MEDIA: (media_artifacts, media_artifacts.c.created_at),
            RetentionResource.INVENTED_TRANSCRIPT: (transcripts, transcripts.c.created_at),
            RetentionResource.ACCEPTED_ANALYSIS: (analyses, analyses.c.created_at),
            RetentionResource.DAILY_REPORT: (daily_reports, daily_reports.c.generated_at),
            RetentionResource.PROCESSING_ATTEMPT: (
                processing_attempts,
                processing_attempts.c.started_at,
            ),
            RetentionResource.MANUAL_UPLOAD_RECEIPT: (
                manual_upload_receipts,
                manual_upload_receipts.c.created_at,
            ),
            RetentionResource.REVIEWER_FEEDBACK: (review_events, review_events.c.created_at),
            RetentionResource.PLAYBOOK_VERSION: (
                playbook_versions,
                playbook_versions.c.created_at,
            ),
            RetentionResource.AUDIT_METADATA: (audit_events, audit_events.c.created_at),
        }

    def evaluate_retention(self, *, principal: DemoPrincipal) -> RetentionRunResult:
        configuration = self.current_configuration()
        now = self.clock.now()
        evaluated = scheduled = not_due = 0
        with self.engine.begin() as connection:
            for resource, (table, timestamp_column) in self._inventory_queries().items():
                rows = connection.execute(
                    sa.select(table.c.id, timestamp_column.label("created_at")).where(
                        ~sa.exists(
                            sa.select(retention_jobs.c.id).where(
                                retention_jobs.c.resource_type == resource.value,
                                retention_jobs.c.resource_id == table.c.id,
                            )
                        )
                    )
                ).all()
                cutoff = now - timedelta(
                    days=configuration.configuration.retention.days_for(resource)
                )
                for row in rows:
                    evaluated += 1
                    created_at = cast(datetime, row.created_at)
                    if created_at > cutoff:
                        not_due += 1
                        continue
                    resource_id = str(row.id)
                    job_id = hashlib.sha256(f"{resource.value}:{resource_id}".encode()).hexdigest()[
                        :32
                    ]
                    result = connection.execute(
                        insert(retention_jobs)
                        .values(
                            id=job_id,
                            resource_type=resource.value,
                            resource_id=resource_id,
                            configuration_version=configuration.version,
                            state=DeletionState.SCHEDULED.value,
                            attempt_count=0,
                            diagnostic_code=None,
                            scheduled_at=now,
                            next_attempt_at=now,
                            completed_at=None,
                            updated_at=now,
                        )
                        .on_conflict_do_nothing(index_elements=["resource_type", "resource_id"])
                    )
                    if result.rowcount:
                        scheduled += 1
                        _audit(
                            connection,
                            principal=principal,
                            action="retention_scheduled",
                            target_type=resource.value,
                            target_id=resource_id,
                            result="scheduled",
                            created_at=now,
                        )
            run_id = _id()
            counts = {
                "evaluated": evaluated,
                "scheduled": scheduled,
                "not_due": not_due,
                "recovered": 0,
                "deleted": 0,
                "retry_scheduled": 0,
                "terminal_failed": 0,
                "retained_exceptions": 0,
            }
            connection.execute(
                maintenance_runs.insert().values(
                    id=run_id,
                    kind=MaintenanceKind.RETENTION_EVALUATION.value,
                    status="passed",
                    safe_counts=counts,
                    principal_id=principal.principal_id.value,
                    role=principal.role.value,
                    started_at=now,
                    completed_at=now,
                )
            )
        return RetentionRunResult(maintenance_run_id=run_id, completed_at=now, **counts)

    def recover_interrupted(self, *, principal: DemoPrincipal) -> int:
        now = self.clock.now()
        with self.engine.begin() as connection:
            rows = connection.execute(
                sa.select(
                    retention_jobs.c.id,
                    retention_jobs.c.resource_type,
                    retention_jobs.c.resource_id,
                )
                .where(retention_jobs.c.state == DeletionState.DELETING.value)
                .with_for_update()
            ).all()
            for row in rows:
                connection.execute(
                    retention_jobs.update()
                    .where(retention_jobs.c.id == row.id)
                    .values(
                        state=DeletionState.RETRY_SCHEDULED.value,
                        diagnostic_code="restart_recovered",
                        next_attempt_at=now,
                        updated_at=now,
                    )
                )
                _audit(
                    connection,
                    principal=principal,
                    action="retention_restart_recovered",
                    target_type=str(row.resource_type),
                    target_id=str(row.resource_id),
                    result="retry_scheduled",
                    created_at=now,
                )
        return len(rows)

    def execute_scheduled(self, *, principal: DemoPrincipal) -> RetentionRunResult:
        started_at = self.clock.now()
        recovered = self.recover_interrupted(principal=principal)
        with self.engine.connect() as connection:
            resource_order = sa.case(
                *(
                    (retention_jobs.c.resource_type == resource.value, position)
                    for position, resource in enumerate(RetentionResource)
                ),
                else_=len(RetentionResource),
            )
            job_ids = tuple(
                connection.execute(
                    sa.select(retention_jobs.c.id)
                    .where(
                        retention_jobs.c.state.in_(
                            [DeletionState.SCHEDULED.value, DeletionState.RETRY_SCHEDULED.value]
                        ),
                        sa.or_(
                            retention_jobs.c.next_attempt_at.is_(None),
                            retention_jobs.c.next_attempt_at <= started_at,
                        ),
                    )
                    .order_by(
                        retention_jobs.c.scheduled_at,
                        resource_order,
                        retention_jobs.c.id,
                    )
                ).scalars()
            )
        deleted = retry_scheduled = terminal_failed = retained_exceptions = 0
        for job_id in job_ids:
            outcome = self._execute_one(str(job_id), principal=principal)
            if outcome is DeletionState.DELETED:
                deleted += 1
            elif outcome is DeletionState.RETRY_SCHEDULED:
                retry_scheduled += 1
            elif outcome is DeletionState.DELETION_FAILED:
                terminal_failed += 1
            elif outcome is DeletionState.RETAINED_EXCEPTION:
                retained_exceptions += 1
        completed_at = self.clock.now()
        counts = {
            "evaluated": 0,
            "scheduled": 0,
            "not_due": 0,
            "recovered": recovered,
            "deleted": deleted,
            "retry_scheduled": retry_scheduled,
            "terminal_failed": terminal_failed,
            "retained_exceptions": retained_exceptions,
        }
        run_id = _id()
        with self.engine.begin() as connection:
            connection.execute(
                maintenance_runs.insert().values(
                    id=run_id,
                    kind=MaintenanceKind.DELETION_EXECUTION.value,
                    status="passed",
                    safe_counts=counts,
                    principal_id=principal.principal_id.value,
                    role=principal.role.value,
                    started_at=started_at,
                    completed_at=completed_at,
                )
            )
        return RetentionRunResult(maintenance_run_id=run_id, completed_at=completed_at, **counts)

    def run_retention(self, *, principal: DemoPrincipal) -> RetentionRunResult:
        evaluation = self.evaluate_retention(principal=principal)
        execution = self.execute_scheduled(principal=principal)
        return RetentionRunResult(
            maintenance_run_id=execution.maintenance_run_id,
            evaluated=evaluation.evaluated,
            scheduled=evaluation.scheduled,
            not_due=evaluation.not_due,
            recovered=execution.recovered,
            deleted=execution.deleted,
            retry_scheduled=execution.retry_scheduled,
            terminal_failed=execution.terminal_failed,
            retained_exceptions=execution.retained_exceptions,
            completed_at=execution.completed_at,
        )

    def _job(self, connection: sa.Connection, job_id: str, *, lock: bool) -> DeletionJob | None:
        query = sa.select(retention_jobs).where(retention_jobs.c.id == job_id)
        if lock:
            query = query.with_for_update()
        row = connection.execute(query).mappings().one_or_none()
        return self._deletion_job(row) if row is not None else None

    @staticmethod
    def _deletion_job(row: sa.RowMapping) -> DeletionJob:
        return DeletionJob(
            job_id=str(row["id"]),
            resource_type=RetentionResource(str(row["resource_type"])),
            resource_id=str(row["resource_id"]),
            configuration_version=int(row["configuration_version"]),
            state=DeletionState(str(row["state"])),
            attempt_count=int(row["attempt_count"]),
            diagnostic_code=cast(str | None, row["diagnostic_code"]),
            scheduled_at=cast(datetime, row["scheduled_at"]),
            next_attempt_at=cast(datetime | None, row["next_attempt_at"]),
            completed_at=cast(datetime | None, row["completed_at"]),
        )

    def deletion_jobs(self) -> tuple[DeletionJob, ...]:
        with self.engine.connect() as connection:
            rows = (
                connection.execute(
                    sa.select(retention_jobs).order_by(
                        retention_jobs.c.scheduled_at.desc(), retention_jobs.c.id
                    )
                )
                .mappings()
                .all()
            )
        return tuple(self._deletion_job(row) for row in rows)

    def retry_deletion(self, job_id: str, *, principal: DemoPrincipal) -> DeletionJob:
        now = self.clock.now()
        with self.engine.begin() as connection:
            job = self._job(connection, job_id, lock=True)
            if job is None:
                raise LookupError("deletion_job_not_found")
            if job.state is not DeletionState.RETRY_SCHEDULED:
                raise ValueError("deletion_job_not_retryable")
            connection.execute(
                retention_jobs.update()
                .where(retention_jobs.c.id == job_id)
                .values(next_attempt_at=now, updated_at=now)
            )
            _audit(
                connection,
                principal=principal,
                action="retention_retry_requested",
                target_type=job.resource_type.value,
                target_id=job.resource_id,
                result="scheduled",
                created_at=now,
            )
        self._execute_one(job_id, principal=principal)
        with self.engine.connect() as connection:
            result = self._job(connection, job_id, lock=False)
        if result is None:
            raise RuntimeError("deletion_job_unavailable")
        return result

    def _execute_one(self, job_id: str, *, principal: DemoPrincipal) -> DeletionState:
        now = self.clock.now()
        with self.engine.begin() as connection:
            job = self._job(connection, job_id, lock=True)
            if job is None:
                raise LookupError("deletion_job_not_found")
            if job.state in {
                DeletionState.DELETED,
                DeletionState.DELETION_FAILED,
                DeletionState.RETAINED_EXCEPTION,
            }:
                return job.state
            connection.execute(
                retention_jobs.update()
                .where(retention_jobs.c.id == job_id)
                .values(state=DeletionState.DELETING.value, updated_at=now)
            )
            _audit(
                connection,
                principal=principal,
                action="retention_deletion_started",
                target_type=job.resource_type.value,
                target_id=job.resource_id,
                result="deleting",
                created_at=now,
            )
        diagnostic = self.failure_plan.diagnostic_for(job)
        if diagnostic is not None:
            return self._record_failure(job, diagnostic=diagnostic, principal=principal)
        try:
            retained_exception = self._destroy(job, principal=principal)
        except OSError:
            return self._record_failure(
                job, diagnostic="local_media_cleanup_unavailable", principal=principal
            )
        state = DeletionState.RETAINED_EXCEPTION if retained_exception else DeletionState.DELETED
        return state

    def _record_failure(
        self, job: DeletionJob, *, diagnostic: str, principal: DemoPrincipal
    ) -> DeletionState:
        now = self.clock.now()
        attempt_count = job.attempt_count + 1
        terminal = attempt_count >= MAX_DELETION_ATTEMPTS
        state = DeletionState.DELETION_FAILED if terminal else DeletionState.RETRY_SCHEDULED
        with self.engine.begin() as connection:
            connection.execute(
                retention_jobs.update()
                .where(retention_jobs.c.id == job.job_id)
                .values(
                    state=state.value,
                    attempt_count=attempt_count,
                    diagnostic_code=diagnostic,
                    next_attempt_at=None if terminal else now + timedelta(minutes=attempt_count),
                    completed_at=now if terminal else None,
                    updated_at=now,
                )
            )
            _audit(
                connection,
                principal=principal,
                action="retention_deletion_failed" if terminal else "retention_retry_scheduled",
                target_type=job.resource_type.value,
                target_id=job.resource_id,
                result="terminal" if terminal else "retry_scheduled",
                created_at=now,
            )
        return state

    def _destroy(self, job: DeletionJob, *, principal: DemoPrincipal) -> bool:
        now = self.clock.now()
        if job.resource_type is RetentionResource.GENERATED_MEDIA:
            self._delete_local_media(job.resource_id, now=now)
        retained_exception = job.resource_type is RetentionResource.AUDIT_METADATA
        with self.engine.begin() as connection:
            connection.execute(
                sa.text("SET LOCAL colacci.retention_authorized = 'slice5a-local-only'")
            )
            if not retained_exception:
                self._destroy_content(connection, job)
            connection.execute(
                insert(retention_tombstones)
                .values(
                    id=hashlib.sha256(
                        f"tombstone:{job.resource_type.value}:{job.resource_id}".encode()
                    ).hexdigest()[:32],
                    resource_type=job.resource_type.value,
                    resource_id=job.resource_id,
                    configuration_version=job.configuration_version,
                    result="retained_exception" if retained_exception else "content_destroyed",
                    exception_code="append_only_audit_metadata" if retained_exception else None,
                    destroyed_at=now,
                )
                .on_conflict_do_nothing(index_elements=["resource_type", "resource_id"])
            )
            state = (
                DeletionState.RETAINED_EXCEPTION if retained_exception else DeletionState.DELETED
            )
            connection.execute(
                retention_jobs.update()
                .where(retention_jobs.c.id == job.job_id)
                .values(
                    state=state.value,
                    attempt_count=job.attempt_count + 1,
                    diagnostic_code=("append_only_audit_metadata" if retained_exception else None),
                    next_attempt_at=None,
                    completed_at=now,
                    updated_at=now,
                )
            )
            _audit(
                connection,
                principal=principal,
                action=(
                    "retention_exception_recorded"
                    if retained_exception
                    else "retention_content_destroyed"
                ),
                target_type=job.resource_type.value,
                target_id=job.resource_id,
                result="retained_exception" if retained_exception else "deleted",
                created_at=now,
            )
        return retained_exception

    def _delete_local_media(self, artifact_id: str, *, now: datetime) -> None:
        with self.engine.connect() as connection:
            row = connection.execute(
                sa.select(
                    manual_upload_receipts.c.object_id,
                    manual_upload_receipts.c.artifact_id,
                ).where(manual_upload_receipts.c.artifact_id == artifact_id)
            ).one_or_none()
        if row is None or row.object_id is None:
            return
        store = LocalSyntheticObjectStore(
            self.settings.manual_upload_root, profile=self.settings.app_profile
        )
        event = store.delete(
            TemporaryObjectReference(
                object_id=str(row.object_id),
                artifact_id=str(row.artifact_id),
                store_name="local-synthetic-v1",
                synthetic=True,
                created_at=now,
            )
        )
        if not event.deletion_confirmed:
            raise OSError("local media cleanup failed")

    @staticmethod
    def _destroy_content(connection: sa.Connection, job: DeletionJob) -> None:
        marker = {"retention_state": "content_destroyed", "synthetic": True}
        resource = job.resource_type
        resource_id = job.resource_id
        if resource is RetentionResource.GENERATED_MEDIA:
            connection.execute(
                transcription_provider_attempts.delete().where(
                    transcription_provider_attempts.c.artifact_id == resource_id
                )
            )
            connection.execute(
                media_lifecycle_events.delete().where(
                    media_lifecycle_events.c.artifact_id == resource_id
                )
            )
            connection.execute(media_artifacts.delete().where(media_artifacts.c.id == resource_id))
        elif resource is RetentionResource.INVENTED_TRANSCRIPT:
            connection.execute(
                transcripts.update()
                .where(transcripts.c.id == resource_id)
                .values(original_payload=marker)
            )
        elif resource is RetentionResource.ACCEPTED_ANALYSIS:
            connection.execute(
                analyses.update()
                .where(analyses.c.id == resource_id)
                .values(original_payload=marker)
            )
        elif resource is RetentionResource.DAILY_REPORT:
            connection.execute(
                daily_report_items.update()
                .where(daily_report_items.c.report_id == resource_id)
                .values(item_payload=marker)
            )
            connection.execute(
                daily_reports.update()
                .where(daily_reports.c.id == resource_id)
                .values(snapshot_payload=marker)
            )
        elif resource is RetentionResource.PROCESSING_ATTEMPT:
            connection.execute(
                processing_attempts.update()
                .where(processing_attempts.c.id == resource_id)
                .values(provenance_payload=marker)
            )
        elif resource is RetentionResource.MANUAL_UPLOAD_RECEIPT:
            connection.execute(
                manual_upload_receipts.update()
                .where(manual_upload_receipts.c.id == resource_id)
                .values(
                    validation_summary=marker,
                    object_id=None,
                    deletion_confirmed=True,
                )
            )
        elif resource is RetentionResource.REVIEWER_FEEDBACK:
            connection.execute(
                review_events.update().where(review_events.c.id == resource_id).values(note=None)
            )
        elif resource is RetentionResource.PLAYBOOK_VERSION:
            connection.execute(
                playbook_versions.update()
                .where(playbook_versions.c.id == resource_id)
                .values(structured_payload=marker)
            )

    def operations_overview(self, *, principal: DemoPrincipal) -> OperationsOverview:
        configuration = self.current_configuration()
        failure_states = (
            "AUDIO_INVALID",
            "TRANSCRIPTION_FAILED",
            "OUTPUT_VALIDATION_FAILED",
            "ANALYSIS_FAILED",
        )
        with self.engine.connect() as connection:
            state_rows = connection.execute(
                sa.select(calls.c.state, sa.func.count().label("count"))
                .where(calls.c.is_synthetic.is_(True))
                .group_by(calls.c.state)
                .order_by(calls.c.state)
            ).all()
            success_count = int(
                connection.execute(
                    sa.select(sa.func.count()).select_from(calls).where(calls.c.state == "ANALYZED")
                ).scalar_one()
            )
            failure_count = int(
                connection.execute(
                    sa.select(sa.func.count())
                    .select_from(calls)
                    .where(calls.c.state.in_(failure_states))
                ).scalar_one()
            )
            retry_count = int(
                connection.execute(
                    sa.select(sa.func.count())
                    .select_from(processing_attempts)
                    .where(processing_attempts.c.attempt_number > 1)
                ).scalar_one()
            )
            latency_rows = connection.execute(
                sa.select(
                    processing_attempts.c.started_at,
                    processing_attempts.c.completed_at,
                ).where(processing_attempts.c.completed_at.is_not(None))
            ).all()
            latest_report = connection.execute(
                sa.select(daily_reports.c.snapshot_payload)
                .where(
                    ~sa.exists(
                        sa.select(retention_tombstones.c.id).where(
                            retention_tombstones.c.resource_type
                            == RetentionResource.DAILY_REPORT.value,
                            retention_tombstones.c.resource_id == daily_reports.c.id,
                        )
                    )
                )
                .order_by(daily_reports.c.generated_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            pending = int(
                connection.execute(
                    sa.select(sa.func.count())
                    .select_from(retention_jobs)
                    .where(
                        retention_jobs.c.state.in_(
                            [
                                DeletionState.SCHEDULED.value,
                                DeletionState.DELETING.value,
                                DeletionState.RETRY_SCHEDULED.value,
                            ]
                        )
                    )
                ).scalar_one()
            )
            failed = int(
                connection.execute(
                    sa.select(sa.func.count())
                    .select_from(retention_jobs)
                    .where(retention_jobs.c.state == DeletionState.DELETION_FAILED.value)
                ).scalar_one()
            )
            explanations = tuple(
                str(item)
                for item in connection.execute(
                    sa.select(retention_jobs.c.diagnostic_code)
                    .where(
                        retention_jobs.c.state == DeletionState.DELETION_FAILED.value,
                        retention_jobs.c.diagnostic_code.is_not(None),
                    )
                    .distinct()
                    .order_by(retention_jobs.c.diagnostic_code)
                ).scalars()
            )
            last_maintenance = connection.execute(
                sa.select(maintenance_runs.c.completed_at)
                .where(maintenance_runs.c.status == "passed")
                .order_by(maintenance_runs.c.completed_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            backup_status = connection.execute(
                sa.select(backup_restore_drills.c.status)
                .order_by(backup_restore_drills.c.completed_at.desc())
                .limit(1)
            ).scalar_one_or_none()
        reconciliation = self._safe_reconciliation(latest_report)
        latency_values = [
            max(
                0,
                int(
                    (
                        cast(datetime, row.completed_at) - cast(datetime, row.started_at)
                    ).total_seconds()
                    * 1000
                ),
            )
            for row in latency_rows
        ]
        permitted = operations_actions(principal.role)
        return OperationsOverview(
            environment="Local development",
            data_label="Synthetic demo data",
            configuration_version=configuration.version,
            processing_volume=tuple(
                SafeStateCount(
                    state=str(row._mapping["state"]).lower(),
                    count=int(row._mapping["count"]),
                )
                for row in state_rows
            ),
            processing_latency=SafeLatencyMetrics(
                completed_attempts=len(latency_values),
                average_milliseconds=(
                    sum(latency_values) // len(latency_values) if latency_values else 0
                ),
                maximum_milliseconds=max(latency_values, default=0),
            ),
            success_count=success_count,
            failure_count=failure_count,
            retry_count=retry_count,
            reconciliation=reconciliation,
            pending_deletions=pending,
            failed_deletions=failed,
            retention_policy_status="active_local_synthetic_policy",
            backup_restore_status=str(backup_status or "not_run"),
            last_successful_maintenance_at=cast(datetime | None, last_maintenance),
            failure_explanations=explanations,
            permitted_actions=permitted,
            external_requests=0,
        )

    @staticmethod
    def _safe_reconciliation(payload: object) -> ReconciliationMetrics:
        if not isinstance(payload, dict):
            return ReconciliationMetrics(
                available=False,
                expected=0,
                received=0,
                analyzed=0,
                failed=0,
                missing=0,
                exact=False,
            )
        completeness = payload.get("completeness")
        source = completeness.get("reconciliation") if isinstance(completeness, dict) else None
        if not isinstance(source, dict):
            raise ValueError("reconciliation_payload_invalid")
        values: dict[str, int] = {}
        for key in ("expected", "received", "analyzed", "failed", "missing"):
            value = source.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("reconciliation_payload_invalid")
            values[key] = value
        expected = values["expected"]
        received = values["received"]
        analyzed = values["analyzed"]
        failed = values["failed"]
        missing = values["missing"]
        return ReconciliationMetrics(
            available=True,
            expected=expected,
            received=received,
            analyzed=analyzed,
            failed=failed,
            missing=missing,
            exact=missing == expected - received and analyzed + failed <= received,
        )

    def run_backup_restore_drill(self, *, principal: DemoPrincipal) -> BackupRestoreDrillResult:
        if not has_permission(principal.role, DemoPermission.USE_OPERATIONS):
            raise PermissionError("backup_restore_drill_forbidden")
        now = self.clock.now()
        before = self._normal_database_signature()
        drill_root = Path(tempfile.mkdtemp(prefix="colacci-law-slice5a-drill-"))
        os.chmod(drill_root, 0o700)
        source_path = drill_root / "source.db"
        backup_path = drill_root / "private-backup.db"
        restore_path = drill_root / "isolated-restore.db"
        drill_id = _id()
        try:
            source = sqlite3.connect(source_path)
            try:
                source.execute(
                    "CREATE TABLE synthetic_records "
                    "(id TEXT PRIMARY KEY, expires_at TEXT NOT NULL, exception INTEGER NOT NULL)"
                )
                source.executemany(
                    "INSERT INTO synthetic_records VALUES (?, ?, ?)",
                    [
                        ("retained-a", (now + timedelta(days=1)).isoformat(), 0),
                        ("retained-b", (now + timedelta(days=2)).isoformat(), 0),
                        ("expired-a", (now - timedelta(days=2)).isoformat(), 0),
                        ("expired-b", (now - timedelta(days=1)).isoformat(), 0),
                        ("audit-exception", (now - timedelta(days=1)).isoformat(), 1),
                    ],
                )
                source.commit()
                backup = sqlite3.connect(backup_path)
                try:
                    source.backup(backup)
                finally:
                    backup.close()
            finally:
                source.close()
            os.chmod(backup_path, 0o600)
            private_backup = sqlite3.connect(backup_path)
            restored = sqlite3.connect(restore_path)
            try:
                private_backup.backup(restored)
                restored.execute(
                    "DELETE FROM synthetic_records WHERE expires_at <= ? AND exception = 0",
                    (now.isoformat(),),
                )
                restored.commit()
                restored_retained = int(
                    restored.execute(
                        "SELECT COUNT(*) FROM synthetic_records WHERE expires_at > ?",
                        (now.isoformat(),),
                    ).fetchone()[0]
                )
                restored_expired = int(
                    restored.execute(
                        "SELECT COUNT(*) FROM synthetic_records "
                        "WHERE expires_at <= ? AND exception = 0",
                        (now.isoformat(),),
                    ).fetchone()[0]
                )
                exceptions = int(
                    restored.execute(
                        "SELECT COUNT(*) FROM synthetic_records WHERE exception = 1"
                    ).fetchone()[0]
                )
            finally:
                private_backup.close()
                restored.close()
        finally:
            shutil.rmtree(drill_root)
        after = self._normal_database_signature()
        if restored_retained != 2 or restored_expired != 0 or exceptions != 1 or before != after:
            raise RuntimeError("backup_restore_drill_failed")
        completed_at = self.clock.now()
        counts = {
            "seeded_retained": 2,
            "seeded_expired": 2,
            "restored_retained": restored_retained,
            "restored_expired": restored_expired,
            "explicit_exceptions": exceptions,
            "normal_database_unchanged": True,
            "disposable_artifacts_removed": not drill_root.exists(),
        }
        with self.engine.begin() as connection:
            connection.execute(
                backup_restore_drills.insert().values(
                    id=drill_id,
                    status="passed",
                    safe_counts=counts,
                    principal_id=principal.principal_id.value,
                    role=principal.role.value,
                    completed_at=completed_at,
                )
            )
            _audit(
                connection,
                principal=principal,
                action="backup_restore_drill_completed",
                target_type="backup_restore_drill",
                target_id=drill_id,
                result="passed",
                created_at=completed_at,
            )
        return BackupRestoreDrillResult(
            drill_id=drill_id,
            status="passed",
            seeded_retained=2,
            seeded_expired=2,
            restored_retained=restored_retained,
            restored_expired=0,
            explicit_exceptions=exceptions,
            normal_database_unchanged=True,
            disposable_artifacts_removed=True,
            completed_at=completed_at,
        )

    def _normal_database_signature(self) -> tuple[int, ...]:
        tables = (
            calls,
            transcripts,
            analyses,
            daily_reports,
            processing_attempts,
            manual_upload_receipts,
            review_events,
            playbook_versions,
        )
        with self.engine.connect() as connection:
            return tuple(
                int(connection.execute(sa.select(sa.func.count()).select_from(table)).scalar_one())
                for table in tables
            )

    def notification_preview(
        self,
        *,
        principal: DemoPrincipal,
        safe_count: int,
        internal_reference: str,
    ) -> NotificationPreview:
        if self.settings.notification_adapter != "noop":
            raise ValueError("non_local_notifier_forbidden")
        if safe_count < 0:
            raise ValueError("notification_safe_count_invalid")
        now = self.clock.now()
        preview = NotificationPreview(
            preview_id=_id(),
            label="Local preview - nothing sent",
            message="A secure local operational action is ready.",
            safe_count=safe_count,
            internal_reference=internal_reference,
            external_attempts=0,
            created_at=now,
        )
        with self.engine.begin() as connection:
            connection.execute(
                notification_previews.insert().values(
                    id=preview.preview_id,
                    label="local_preview_nothing_sent",
                    message_code="secure_local_action_ready",
                    safe_count=safe_count,
                    internal_reference=internal_reference,
                    external_attempts=0,
                    principal_id=principal.principal_id.value,
                    role=principal.role.value,
                    created_at=now,
                )
            )
            _audit(
                connection,
                principal=principal,
                action="notification_preview_created",
                target_type="notification_preview",
                target_id=preview.preview_id,
                result="nothing_sent",
                created_at=now,
            )
        return preview
