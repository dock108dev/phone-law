"""Strict, content-free contracts for Slice 5A local operations."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, StringConstraints, field_validator, model_validator

from packages.contracts.report import DemoPrincipal, DemoRole
from packages.contracts.review import AnalysisCategory, Direction, StrictModel

SafeId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")]
SafeCode = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{2,63}$")]
SyntheticExtension = Annotated[str, StringConstraints(pattern=r"^SYN-[0-9]{3}$")]


class RetentionResource(StrEnum):
    GENERATED_MEDIA = "generated_media"
    INVENTED_TRANSCRIPT = "invented_transcript"
    ACCEPTED_ANALYSIS = "accepted_analysis"
    DAILY_REPORT = "daily_report"
    PROCESSING_ATTEMPT = "processing_attempt"
    MANUAL_UPLOAD_RECEIPT = "manual_upload_receipt"
    REVIEWER_FEEDBACK = "reviewer_feedback"
    PLAYBOOK_VERSION = "playbook_version"
    AUDIT_METADATA = "audit_metadata"


class DeletionState(StrEnum):
    SCHEDULED = "SCHEDULED"
    DELETING = "DELETING"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    DELETED = "DELETED"
    DELETION_FAILED = "DELETION_FAILED"
    RETAINED_EXCEPTION = "RETAINED_EXCEPTION"


class MaintenanceKind(StrEnum):
    RETENTION_EVALUATION = "retention_evaluation"
    DELETION_EXECUTION = "deletion_execution"
    RECONCILIATION = "reconciliation"
    BACKUP_RESTORE_DRILL = "backup_restore_drill"


class StaffExtensionMapping(StrictModel):
    extension: SyntheticExtension
    synthetic_label: Annotated[str, StringConstraints(pattern=r"^Synthetic staff [A-Z]$")]


class LocalRetentionSchedule(StrictModel):
    generated_media_days: Annotated[int, Field(ge=1, le=3650)]
    invented_transcript_days: Annotated[int, Field(ge=1, le=3650)]
    accepted_analysis_days: Annotated[int, Field(ge=1, le=3650)]
    daily_report_days: Annotated[int, Field(ge=1, le=3650)]
    processing_attempt_days: Annotated[int, Field(ge=1, le=3650)]
    manual_upload_receipt_days: Annotated[int, Field(ge=1, le=3650)]
    reviewer_feedback_days: Annotated[int, Field(ge=1, le=3650)]
    playbook_version_days: Annotated[int, Field(ge=1, le=3650)]
    audit_metadata_days: Annotated[int, Field(ge=1, le=3650)]

    def days_for(self, resource: RetentionResource) -> int:
        return {
            RetentionResource.GENERATED_MEDIA: self.generated_media_days,
            RetentionResource.INVENTED_TRANSCRIPT: self.invented_transcript_days,
            RetentionResource.ACCEPTED_ANALYSIS: self.accepted_analysis_days,
            RetentionResource.DAILY_REPORT: self.daily_report_days,
            RetentionResource.PROCESSING_ATTEMPT: self.processing_attempt_days,
            RetentionResource.MANUAL_UPLOAD_RECEIPT: self.manual_upload_receipt_days,
            RetentionResource.REVIEWER_FEEDBACK: self.reviewer_feedback_days,
            RetentionResource.PLAYBOOK_VERSION: self.playbook_version_days,
            RetentionResource.AUDIT_METADATA: self.audit_metadata_days,
        }[resource]


class LocalFirmConfiguration(StrictModel):
    schema_version: Literal["local-firm-configuration-v1"]
    firm_timezone: Literal["America/New_York"]
    daily_report_cutoff: Annotated[
        str, StringConstraints(pattern=r"^(0[0-9]|1[0-9]|2[0-3]):[0-5][0-9]$")
    ]
    eligible_call_directions: tuple[Direction, ...]
    eligible_call_categories: tuple[AnalysisCategory, ...]
    staff_extension_mappings: tuple[StaffExtensionMapping, ...]
    report_roles: tuple[DemoRole, ...]
    synthetic_playbook_version: Annotated[
        str, StringConstraints(pattern=r"^synthetic-[a-z0-9._-]{3,64}$")
    ]
    retention: LocalRetentionSchedule
    deletion_behavior: Literal["scheduled_content_destruction_with_tombstone"]
    notification_preference: Literal["local_preview_noop"]

    @field_validator("eligible_call_directions", mode="before")
    @classmethod
    def parse_directions(cls, value: object) -> object:
        if isinstance(value, list | tuple):
            return tuple(Direction(item) if isinstance(item, str) else item for item in value)
        return value

    @field_validator("eligible_call_categories", mode="before")
    @classmethod
    def parse_categories(cls, value: object) -> object:
        if isinstance(value, list | tuple):
            return tuple(
                AnalysisCategory(item) if isinstance(item, str) else item for item in value
            )
        return value

    @field_validator("report_roles", mode="before")
    @classmethod
    def parse_report_roles(cls, value: object) -> object:
        if isinstance(value, list | tuple):
            return tuple(DemoRole(item) if isinstance(item, str) else item for item in value)
        return value

    @field_validator("staff_extension_mappings", mode="before")
    @classmethod
    def parse_staff_mappings(cls, value: object) -> object:
        if isinstance(value, list | tuple):
            return tuple(
                StaffExtensionMapping.model_validate(item) if isinstance(item, dict) else item
                for item in value
            )
        return value

    @model_validator(mode="after")
    def local_values_are_complete_and_unique(self) -> LocalFirmConfiguration:
        if not self.eligible_call_directions or len(set(self.eligible_call_directions)) != len(
            self.eligible_call_directions
        ):
            raise ValueError("eligible call directions must be nonempty and unique")
        if not self.eligible_call_categories or len(set(self.eligible_call_categories)) != len(
            self.eligible_call_categories
        ):
            raise ValueError("eligible call categories must be nonempty and unique")
        extensions = [item.extension for item in self.staff_extension_mappings]
        if not extensions or len(set(extensions)) != len(extensions):
            raise ValueError("synthetic staff extension mappings must be nonempty and unique")
        if set(self.report_roles) != set(DemoRole):
            raise ValueError("local report roles must contain all demo roles exactly once")
        return self


DEFAULT_LOCAL_FIRM_CONFIGURATION = LocalFirmConfiguration(
    schema_version="local-firm-configuration-v1",
    firm_timezone="America/New_York",
    daily_report_cutoff="18:00",
    eligible_call_directions=(Direction.INBOUND, Direction.OUTBOUND, Direction.UNKNOWN),
    eligible_call_categories=tuple(AnalysisCategory),
    staff_extension_mappings=(
        StaffExtensionMapping(extension="SYN-101", synthetic_label="Synthetic staff A"),
        StaffExtensionMapping(extension="SYN-104", synthetic_label="Synthetic staff B"),
    ),
    report_roles=(DemoRole.REVIEWER, DemoRole.ADMINISTRATOR, DemoRole.OPERATIONS),
    synthetic_playbook_version="synthetic-draft-v1",
    retention=LocalRetentionSchedule(
        generated_media_days=7,
        invented_transcript_days=30,
        accepted_analysis_days=90,
        daily_report_days=90,
        processing_attempt_days=30,
        manual_upload_receipt_days=30,
        reviewer_feedback_days=180,
        playbook_version_days=365,
        audit_metadata_days=3650,
    ),
    deletion_behavior="scheduled_content_destruction_with_tombstone",
    notification_preference="local_preview_noop",
)


class ConfigurationVersion(StrictModel):
    configuration_id: SafeId
    version: Annotated[int, Field(ge=1)]
    configuration: LocalFirmConfiguration
    principal: DemoPrincipal
    content_hash_reference: Annotated[str, StringConstraints(pattern=r"^sha256:[a-f0-9]{12}$")]
    created_at: AwareDatetime


class ConfigurationHistory(StrictModel):
    current_version: Annotated[int, Field(ge=1)]
    versions: tuple[ConfigurationVersion, ...]


class DeletionJob(StrictModel):
    job_id: SafeId
    resource_type: RetentionResource
    resource_id: SafeId
    configuration_version: Annotated[int, Field(ge=1)]
    state: DeletionState
    attempt_count: Annotated[int, Field(ge=0, le=3)]
    diagnostic_code: SafeCode | None = None
    scheduled_at: AwareDatetime
    next_attempt_at: AwareDatetime | None = None
    completed_at: AwareDatetime | None = None


class RetentionRunResult(StrictModel):
    maintenance_run_id: SafeId
    evaluated: Annotated[int, Field(ge=0)]
    scheduled: Annotated[int, Field(ge=0)]
    not_due: Annotated[int, Field(ge=0)]
    recovered: Annotated[int, Field(ge=0)]
    deleted: Annotated[int, Field(ge=0)]
    retry_scheduled: Annotated[int, Field(ge=0)]
    terminal_failed: Annotated[int, Field(ge=0)]
    retained_exceptions: Annotated[int, Field(ge=0)]
    completed_at: AwareDatetime


class ReconciliationMetrics(StrictModel):
    expected: Annotated[int, Field(ge=0)]
    received: Annotated[int, Field(ge=0)]
    analyzed: Annotated[int, Field(ge=0)]
    failed: Annotated[int, Field(ge=0)]
    missing: Annotated[int, Field(ge=0)]
    exact: bool


class SafeStateCount(StrictModel):
    state: SafeId
    count: Annotated[int, Field(ge=0)]


class OperationsOverview(StrictModel):
    environment: Literal["Local development"]
    data_label: Literal["Synthetic demo data"]
    configuration_version: Annotated[int, Field(ge=1)]
    processing_volume: tuple[SafeStateCount, ...]
    success_count: Annotated[int, Field(ge=0)]
    failure_count: Annotated[int, Field(ge=0)]
    retry_count: Annotated[int, Field(ge=0)]
    reconciliation: ReconciliationMetrics
    pending_deletions: Annotated[int, Field(ge=0)]
    failed_deletions: Annotated[int, Field(ge=0)]
    retention_policy_status: Literal["active_local_synthetic_policy"]
    backup_restore_status: SafeId
    last_successful_maintenance_at: AwareDatetime | None = None
    failure_explanations: tuple[SafeCode, ...]
    permitted_actions: tuple[SafeCode, ...]
    external_requests: Literal[0] = 0


class BackupRestoreDrillResult(StrictModel):
    drill_id: SafeId
    status: Literal["passed"]
    seeded_retained: Annotated[int, Field(ge=1)]
    seeded_expired: Annotated[int, Field(ge=1)]
    restored_retained: Annotated[int, Field(ge=1)]
    restored_expired: Literal[0]
    explicit_exceptions: Annotated[int, Field(ge=1)]
    normal_database_unchanged: Literal[True]
    disposable_artifacts_removed: Literal[True]
    completed_at: AwareDatetime


class NotificationPreview(StrictModel):
    preview_id: SafeId
    label: Literal["Local preview - nothing sent"]
    message: Literal["A secure local operational action is ready."]
    safe_count: Annotated[int, Field(ge=0)]
    internal_reference: SafeId
    external_attempts: Literal[0]
    created_at: AwareDatetime
