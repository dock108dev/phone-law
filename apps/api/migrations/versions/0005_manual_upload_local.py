"""Add content-free local synthetic manual-upload receipts and state history."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_manual_upload_local"
down_revision: str | None = "0004_offline_transcription_readiness"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "manual_upload_receipts",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("client_submission_id", sa.String(64), nullable=False),
        sa.Column("source_event_id", sa.String(128), nullable=False),
        sa.Column("call_id", sa.String(32), sa.ForeignKey("calls.id"), nullable=True),
        sa.Column("submission_kind", sa.String(32), nullable=False),
        sa.Column("is_synthetic", sa.Boolean, nullable=False),
        sa.Column("content_fingerprint", sa.String(64), nullable=False),
        sa.Column("language_hint", sa.String(8), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("staff_extension", sa.String(16), nullable=False),
        sa.Column("principal_id", sa.String(64), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("attempt_number", sa.Integer, nullable=False),
        sa.Column("diagnostic_code", sa.String(64), nullable=True),
        sa.Column("retryable", sa.Boolean, nullable=False),
        sa.Column("object_id", sa.String(32), nullable=True),
        sa.Column("artifact_id", sa.String(32), nullable=True),
        sa.Column("validation_summary", postgresql.JSONB, nullable=False),
        sa.Column("deletion_confirmed", sa.Boolean, nullable=True),
        sa.Column("adapter_version", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("is_synthetic", name="ck_manual_upload_synthetic_only"),
        sa.CheckConstraint(
            "submission_kind IN ('synthetic_audio', 'transcript_only')",
            name="ck_manual_upload_kind",
        ),
        sa.CheckConstraint(
            "role IN ('administrator', 'operations')", name="ck_manual_upload_role"
        ),
        sa.CheckConstraint(
            "attempt_number BETWEEN 0 AND 3", name="ck_manual_upload_attempt_bounded"
        ),
        sa.CheckConstraint(
            "staff_extension ~ '^SYN-[0-9]{3}$'", name="ck_manual_upload_synthetic_extension"
        ),
        sa.CheckConstraint(
            "content_fingerprint ~ '^[a-f0-9]{64}$'", name="ck_manual_upload_fingerprint"
        ),
        sa.CheckConstraint(
            "(submission_kind = 'synthetic_audio' AND artifact_id IS NOT NULL "
            "AND (object_id IS NOT NULL OR deletion_confirmed IS TRUE)) "
            "OR (submission_kind = 'transcript_only' AND object_id IS NULL AND artifact_id IS NULL)",
            name="ck_manual_upload_object_shape",
        ),
        sa.UniqueConstraint("client_submission_id", name="uq_manual_upload_submission"),
        sa.UniqueConstraint("content_fingerprint", name="uq_manual_upload_content"),
        sa.UniqueConstraint("source_event_id", name="uq_manual_upload_source_event"),
    )
    op.create_index(
        "ix_manual_upload_state_updated", "manual_upload_receipts", ["state", "updated_at"]
    )
    op.create_table(
        "manual_upload_state_events",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "upload_id",
            sa.String(32),
            sa.ForeignKey("manual_upload_receipts.id"),
            nullable=False,
        ),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("attempt_number", sa.Integer, nullable=False),
        sa.Column("diagnostic_code", sa.String(64), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "attempt_number BETWEEN 0 AND 3", name="ck_manual_upload_event_attempt_bounded"
        ),
    )
    op.create_index(
        "ix_manual_upload_events_upload",
        "manual_upload_state_events",
        ["upload_id", "occurred_at"],
    )
    op.execute(
        "CREATE TRIGGER immutable_manual_upload_state_events BEFORE UPDATE OR DELETE "
        "ON manual_upload_state_events FOR EACH ROW "
        "EXECUTE FUNCTION prevent_immutable_review_record_change()"
    )
    op.execute(
        "UPDATE system_metadata SET value = 'manual_upload_local' "
        "WHERE key = 'schema_purpose'"
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER immutable_manual_upload_state_events ON manual_upload_state_events"
    )
    op.drop_index("ix_manual_upload_events_upload", table_name="manual_upload_state_events")
    op.drop_table("manual_upload_state_events")
    op.drop_index("ix_manual_upload_state_updated", table_name="manual_upload_receipts")
    op.drop_table("manual_upload_receipts")
    op.execute(
        "UPDATE system_metadata SET value = 'offline_transcription_readiness' "
        "WHERE key = 'schema_purpose'"
    )
