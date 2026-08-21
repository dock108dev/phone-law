"""Add versioned local operations, retention jobs, and content-free evidence."""

from collections.abc import Sequence
from datetime import UTC, datetime
import hashlib
import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_local_operations"
down_revision: str | None = "0005_manual_upload_local"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _default_configuration() -> dict[str, object]:
    return {
        "schema_version": "local-firm-configuration-v1",
        "firm_timezone": "America/New_York",
        "daily_report_cutoff": "18:00",
        "eligible_call_directions": ["inbound", "outbound", "unknown"],
        "eligible_call_categories": [
            "new_intake",
            "existing_client_follow_up",
            "administrative",
            "dissatisfaction_escalation",
            "routine_no_action",
            "unknown",
        ],
        "staff_extension_mappings": [
            {"extension": "SYN-101", "synthetic_label": "Synthetic staff A"},
            {"extension": "SYN-104", "synthetic_label": "Synthetic staff B"},
        ],
        "report_roles": ["reviewer", "administrator", "operations"],
        "synthetic_playbook_version": "synthetic-draft-v1",
        "retention": {
            "generated_media_days": 7,
            "invented_transcript_days": 30,
            "accepted_analysis_days": 90,
            "daily_report_days": 90,
            "processing_attempt_days": 30,
            "manual_upload_receipt_days": 30,
            "reviewer_feedback_days": 180,
            "playbook_version_days": 365,
            "audit_metadata_days": 3650,
        },
        "deletion_behavior": "scheduled_content_destruction_with_tombstone",
        "notification_preference": "local_preview_noop",
    }


def upgrade() -> None:
    op.create_table(
        "firm_configuration_versions",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("version", sa.Integer, nullable=False, unique=True),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("configuration_payload", postgresql.JSONB, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("principal_id", sa.String(64), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_firm_configuration_positive_version"),
        sa.CheckConstraint(
            "schema_version = 'local-firm-configuration-v1'",
            name="ck_firm_configuration_schema",
        ),
        sa.CheckConstraint("role = 'administrator'", name="ck_firm_configuration_admin_only"),
        sa.CheckConstraint(
            "configuration_payload ->> 'firm_timezone' = 'America/New_York'",
            name="ck_firm_configuration_local_timezone",
        ),
        sa.CheckConstraint(
            "configuration_payload ->> 'notification_preference' = 'local_preview_noop'",
            name="ck_firm_configuration_noop_notification",
        ),
        sa.CheckConstraint(
            "configuration_payload ->> 'deletion_behavior' = "
            "'scheduled_content_destruction_with_tombstone'",
            name="ck_firm_configuration_local_deletion",
        ),
    )
    op.create_index(
        "ix_firm_configuration_current", "firm_configuration_versions", ["version"]
    )
    op.create_table(
        "retention_jobs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(128), nullable=False),
        sa.Column("configuration_version", sa.Integer, nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("attempt_count", sa.Integer, nullable=False),
        sa.Column("diagnostic_code", sa.String(64)),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "resource_type IN ('generated_media','invented_transcript','accepted_analysis',"
            "'daily_report','processing_attempt','manual_upload_receipt','reviewer_feedback',"
            "'playbook_version','audit_metadata')",
            name="ck_retention_job_resource",
        ),
        sa.CheckConstraint(
            "state IN ('SCHEDULED','DELETING','RETRY_SCHEDULED','DELETED',"
            "'DELETION_FAILED','RETAINED_EXCEPTION')",
            name="ck_retention_job_state",
        ),
        sa.CheckConstraint(
            "attempt_count BETWEEN 0 AND 3", name="ck_retention_job_bounded_attempts"
        ),
        sa.UniqueConstraint("resource_type", "resource_id", name="uq_retention_job_resource"),
    )
    op.create_index(
        "ix_retention_jobs_runnable",
        "retention_jobs",
        ["state", "next_attempt_at", "scheduled_at"],
    )
    op.create_table(
        "retention_tombstones",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(128), nullable=False),
        sa.Column("configuration_version", sa.Integer, nullable=False),
        sa.Column("result", sa.String(32), nullable=False),
        sa.Column("exception_code", sa.String(64)),
        sa.Column("destroyed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "result IN ('content_destroyed','retained_exception')",
            name="ck_retention_tombstone_result",
        ),
        sa.UniqueConstraint("resource_type", "resource_id", name="uq_tombstone_resource"),
    )
    op.create_index(
        "ix_retention_tombstones_destroyed", "retention_tombstones", ["destroyed_at"]
    )
    op.create_table(
        "maintenance_runs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("safe_counts", postgresql.JSONB, nullable=False),
        sa.Column("principal_id", sa.String(64), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('passed','failed')", name="ck_maintenance_run_status"),
        sa.CheckConstraint(
            "role IN ('administrator','operations')", name="ck_maintenance_run_role"
        ),
    )
    op.create_index("ix_maintenance_runs_completed", "maintenance_runs", ["completed_at"])
    op.create_table(
        "backup_restore_drills",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("safe_counts", postgresql.JSONB, nullable=False),
        sa.Column("principal_id", sa.String(64), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status = 'passed'", name="ck_backup_drill_passed_only"),
        sa.CheckConstraint(
            "role IN ('administrator','operations')", name="ck_backup_drill_role"
        ),
    )
    op.create_table(
        "notification_previews",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("label", sa.String(64), nullable=False),
        sa.Column("message_code", sa.String(64), nullable=False),
        sa.Column("safe_count", sa.Integer, nullable=False),
        sa.Column("internal_reference", sa.String(128), nullable=False),
        sa.Column("external_attempts", sa.Integer, nullable=False),
        sa.Column("principal_id", sa.String(64), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "label = 'local_preview_nothing_sent'", name="ck_notification_preview_label"
        ),
        sa.CheckConstraint(
            "message_code = 'secure_local_action_ready'", name="ck_notification_message"
        ),
        sa.CheckConstraint("safe_count >= 0", name="ck_notification_safe_count"),
        sa.CheckConstraint("external_attempts = 0", name="ck_notification_zero_external"),
    )
    for table in (
        "firm_configuration_versions",
        "retention_tombstones",
        "maintenance_runs",
        "backup_restore_drills",
        "notification_previews",
    ):
        op.execute(
            f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION prevent_immutable_review_record_change()"
        )
    op.execute(
        """
        CREATE FUNCTION preserve_retention_job_target() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE'
               OR NEW.id <> OLD.id
               OR NEW.resource_type <> OLD.resource_type
               OR NEW.resource_id <> OLD.resource_id
               OR NEW.configuration_version <> OLD.configuration_version
               OR NEW.scheduled_at <> OLD.scheduled_at THEN
                RAISE EXCEPTION 'retention job target is immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER immutable_retention_job_target BEFORE UPDATE OR DELETE ON retention_jobs "
        "FOR EACH ROW EXECUTE FUNCTION preserve_retention_job_target()"
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_immutable_review_record_change() RETURNS trigger AS $$
        BEGIN
            IF current_setting('colacci.retention_authorized', true) = 'slice5a-local-only' THEN
                IF TG_OP = 'DELETE' THEN
                    RETURN OLD;
                END IF;
                RETURN NEW;
            END IF;
            RAISE EXCEPTION 'accepted review records are immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION preserve_playbook_content() RETURNS trigger AS $$
        BEGIN
            IF current_setting('colacci.retention_authorized', true) = 'slice5a-local-only' THEN
                IF TG_OP = 'DELETE' THEN
                    RETURN OLD;
                END IF;
                RETURN NEW;
            END IF;
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'playbook rules and instructions are immutable';
            END IF;
            IF NEW.id <> OLD.id
               OR NEW.version <> OLD.version
               OR NEW.is_synthetic <> OLD.is_synthetic
               OR NEW.structured_payload <> OLD.structured_payload
               OR NEW.created_at <> OLD.created_at THEN
                RAISE EXCEPTION 'playbook rules and instructions are immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    payload = _default_configuration()
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    op.get_bind().execute(
        sa.text(
            "INSERT INTO firm_configuration_versions "
            "(id, version, schema_version, configuration_payload, content_hash, principal_id, "
            "role, created_at) VALUES (:id, 1, :schema, CAST(:payload AS jsonb), :hash, "
            "'demo-admin', 'administrator', :created_at)"
        ),
        {
            "id": hashlib.sha256(b"local-firm-configuration-v1").hexdigest()[:32],
            "schema": "local-firm-configuration-v1",
            "payload": serialized,
            "hash": hashlib.sha256(serialized.encode()).hexdigest(),
            "created_at": datetime(2026, 8, 19, 12, tzinfo=UTC),
        },
    )
    op.execute(
        "UPDATE system_metadata SET value = 'local_operations' WHERE key = 'schema_purpose'"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER immutable_retention_job_target ON retention_jobs")
    op.execute("DROP FUNCTION preserve_retention_job_target")
    for table in (
        "notification_previews",
        "backup_restore_drills",
        "maintenance_runs",
        "retention_tombstones",
        "firm_configuration_versions",
    ):
        op.execute(f"DROP TRIGGER immutable_{table} ON {table}")
    op.drop_table("notification_previews")
    op.drop_table("backup_restore_drills")
    op.drop_index("ix_maintenance_runs_completed", table_name="maintenance_runs")
    op.drop_table("maintenance_runs")
    op.drop_index("ix_retention_tombstones_destroyed", table_name="retention_tombstones")
    op.drop_table("retention_tombstones")
    op.drop_index("ix_retention_jobs_runnable", table_name="retention_jobs")
    op.drop_table("retention_jobs")
    op.drop_index("ix_firm_configuration_current", table_name="firm_configuration_versions")
    op.drop_table("firm_configuration_versions")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_immutable_review_record_change() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'accepted review records are immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION preserve_playbook_content() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'playbook rules and instructions are immutable';
            END IF;
            IF NEW.id <> OLD.id
               OR NEW.version <> OLD.version
               OR NEW.is_synthetic <> OLD.is_synthetic
               OR NEW.structured_payload <> OLD.structured_payload
               OR NEW.created_at <> OLD.created_at THEN
                RAISE EXCEPTION 'playbook rules and instructions are immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "UPDATE system_metadata SET value = 'manual_upload_local' WHERE key = 'schema_purpose'"
    )
