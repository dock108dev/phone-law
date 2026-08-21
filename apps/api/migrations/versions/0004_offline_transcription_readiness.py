"""Add immutable, content-free Slice 3A media and provider-attempt metadata."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_offline_transcription_readiness"
down_revision: str | None = "0003_synthetic_review_experience"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The mandated descriptive revision identifier exceeds Alembic's historical
    # 32-character default. Keep the widened column across downgrades so this
    # revision can remain present until Alembic updates it to the prior value.
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(32),
        type_=sa.String(64),
        existing_nullable=False,
    )
    op.create_table(
        "media_artifacts",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("call_id", sa.String(32), sa.ForeignKey("calls.id"), nullable=True),
        sa.Column("is_synthetic", sa.Boolean, nullable=False),
        sa.Column("content_hash_reference", sa.String(19), nullable=False),
        sa.Column("media_format", sa.String(16), nullable=False),
        sa.Column("byte_size", sa.BigInteger, nullable=False),
        sa.Column("duration_seconds", sa.Float, nullable=False),
        sa.Column("channel_count", sa.Integer, nullable=False),
        sa.Column("sample_rate_hz", sa.Integer, nullable=False),
        sa.Column("lifecycle_state", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("is_synthetic", name="ck_media_artifacts_synthetic_only"),
        sa.CheckConstraint("byte_size > 0", name="ck_media_artifacts_positive_size"),
        sa.CheckConstraint("duration_seconds > 0", name="ck_media_artifacts_positive_duration"),
        sa.CheckConstraint("channel_count > 0", name="ck_media_artifacts_positive_channels"),
        sa.CheckConstraint("sample_rate_hz > 0", name="ck_media_artifacts_positive_rate"),
    )
    op.create_index("ix_media_artifacts_state", "media_artifacts", ["lifecycle_state"])
    op.create_table(
        "media_lifecycle_events",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "artifact_id", sa.String(32), sa.ForeignKey("media_artifacts.id"), nullable=False
        ),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("deletion_confirmed", sa.Boolean, nullable=True),
        sa.Column("error_class", sa.String(64), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_media_lifecycle_artifact",
        "media_lifecycle_events",
        ["artifact_id", "occurred_at"],
    )
    op.create_table(
        "transcription_provider_attempts",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "artifact_id", sa.String(32), sa.ForeignKey("media_artifacts.id"), nullable=False
        ),
        sa.Column("call_id", sa.String(32), sa.ForeignKey("calls.id"), nullable=True),
        sa.Column("attempt_number", sa.Integer, nullable=False),
        sa.Column("adapter_version", sa.String(128), nullable=False),
        sa.Column("model_id", sa.String(128), nullable=False),
        sa.Column("provider_response_version", sa.String(128), nullable=True),
        sa.Column("timestamp_availability", sa.String(32), nullable=True),
        sa.Column("diarization_availability", sa.String(32), nullable=True),
        sa.Column("safe_error_class", sa.String(64), nullable=True),
        sa.Column("retryable", sa.Boolean, nullable=False),
        sa.Column("duration_ms", sa.Float, nullable=False),
        sa.Column("input_tokens", sa.Integer, nullable=True),
        sa.Column("output_tokens", sa.Integer, nullable=True),
        sa.Column("usage_duration_seconds", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "attempt_number BETWEEN 1 AND 3", name="ck_provider_attempt_bounded_number"
        ),
        sa.CheckConstraint("duration_ms >= 0", name="ck_provider_attempt_nonnegative_timing"),
        sa.UniqueConstraint(
            "artifact_id", "attempt_number", name="uq_provider_attempt_artifact_number"
        ),
    )
    op.create_index(
        "ix_provider_attempt_artifact",
        "transcription_provider_attempts",
        ["artifact_id", "attempt_number"],
    )
    for table in (
        "media_artifacts",
        "media_lifecycle_events",
        "transcription_provider_attempts",
    ):
        op.execute(
            f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION prevent_immutable_review_record_change()"
        )
    op.execute(
        "UPDATE system_metadata SET value = 'offline_transcription_readiness' "
        "WHERE key = 'schema_purpose'"
    )


def downgrade() -> None:
    for table in (
        "transcription_provider_attempts",
        "media_lifecycle_events",
        "media_artifacts",
    ):
        op.execute(f"DROP TRIGGER immutable_{table} ON {table}")
    op.drop_index("ix_provider_attempt_artifact", table_name="transcription_provider_attempts")
    op.drop_table("transcription_provider_attempts")
    op.drop_index("ix_media_lifecycle_artifact", table_name="media_lifecycle_events")
    op.drop_table("media_lifecycle_events")
    op.drop_index("ix_media_artifacts_state", table_name="media_artifacts")
    op.drop_table("media_artifacts")
    op.execute(
        "UPDATE system_metadata SET value = 'synthetic_review_experience' "
        "WHERE key = 'schema_purpose'"
    )
