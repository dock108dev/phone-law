"""Create immutable synthetic review contracts and persistence."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_synthetic_review_contracts"
down_revision: str | None = "0001_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "calls",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("fixture_id", sa.String(32), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("source_call_id", sa.String(128), nullable=False),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column("is_synthetic", sa.Boolean, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("normalized_payload", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source", "source_call_id", name="uq_calls_source_call"),
    )
    op.create_index("ix_calls_state", "calls", ["state"])
    op.create_index("ix_calls_fixture", "calls", ["fixture_id"])
    op.create_table(
        "ingestion_events",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("call_id", sa.String(32), sa.ForeignKey("calls.id"), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("source_event_id", sa.String(128), nullable=False),
        sa.Column("fixture_id", sa.String(32), nullable=False),
        sa.Column("disposition", sa.String(32), nullable=False),
        sa.Column("duplicate_delivery_count", sa.Integer, server_default="0", nullable=False),
        sa.Column("event_payload", postgresql.JSONB, nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source", "source_event_id", name="uq_ingestion_events_source_event"),
    )
    op.create_index("ix_ingestion_events_call", "ingestion_events", ["call_id"])
    op.create_index("ix_ingestion_events_fixture", "ingestion_events", ["fixture_id"])
    op.create_table(
        "processing_attempts",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("call_id", sa.String(32), sa.ForeignKey("calls.id"), nullable=False),
        sa.Column("attempt_number", sa.Integer, nullable=False),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column("failure_class", sa.String(64)),
        sa.Column("diagnostic_code", sa.String(128)),
        sa.Column("retryable", sa.Boolean),
        sa.Column("provenance_payload", postgresql.JSONB, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("call_id", "attempt_number", name="uq_attempts_call_number"),
    )
    op.create_index("ix_attempts_call_state", "processing_attempts", ["call_id", "state"])
    op.create_table(
        "transcripts",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("call_id", sa.String(32), sa.ForeignKey("calls.id"), nullable=False),
        sa.Column("attempt_id", sa.String(32), sa.ForeignKey("processing_attempts.id"), nullable=False),
        sa.Column("language", sa.String(8), nullable=False),
        sa.Column("original_payload", postgresql.JSONB, nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("adapter_version", sa.String(128), nullable=False),
        sa.Column("model_version", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("call_id", name="uq_transcripts_call"),
        sa.UniqueConstraint("attempt_id", name="uq_transcripts_attempt"),
    )
    op.create_index("ix_transcripts_provenance", "transcripts", ["schema_version", "adapter_version", "model_version"])
    op.create_table(
        "analyses",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("call_id", sa.String(32), sa.ForeignKey("calls.id"), nullable=False),
        sa.Column("attempt_id", sa.String(32), sa.ForeignKey("processing_attempts.id"), nullable=False),
        sa.Column("acceptance_state", sa.String(32), nullable=False),
        sa.Column("original_payload", postgresql.JSONB, nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("prompt_version", sa.String(128), nullable=False),
        sa.Column("playbook_version", sa.String(128), nullable=False),
        sa.Column("adapter_version", sa.String(128), nullable=False),
        sa.Column("model_version", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("acceptance_state = 'accepted'", name="ck_analyses_accepted_only"),
        sa.UniqueConstraint("call_id", name="uq_analyses_call"),
        sa.UniqueConstraint("attempt_id", name="uq_analyses_attempt"),
    )
    op.create_index("ix_analyses_provenance", "analyses", ["schema_version", "prompt_version", "playbook_version", "adapter_version", "model_version"])
    op.create_table(
        "playbook_versions",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("version", sa.String(128), nullable=False, unique=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("is_synthetic", sa.Boolean, nullable=False),
        sa.Column("structured_payload", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.execute(
        """
        CREATE FUNCTION prevent_immutable_review_record_change() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'accepted review records are immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table in ("transcripts", "analyses"):
        op.execute(
            f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION prevent_immutable_review_record_change()"
        )
    op.execute(
        "UPDATE system_metadata SET value = 'synthetic_review_contracts' "
        "WHERE key = 'schema_purpose'"
    )


def downgrade() -> None:
    for table in ("analyses", "transcripts"):
        op.execute(f"DROP TRIGGER immutable_{table} ON {table}")
    op.execute("DROP FUNCTION prevent_immutable_review_record_change")
    op.drop_table("playbook_versions")
    op.drop_index("ix_analyses_provenance", table_name="analyses")
    op.drop_table("analyses")
    op.drop_index("ix_transcripts_provenance", table_name="transcripts")
    op.drop_table("transcripts")
    op.drop_index("ix_attempts_call_state", table_name="processing_attempts")
    op.drop_table("processing_attempts")
    op.drop_index("ix_ingestion_events_fixture", table_name="ingestion_events")
    op.drop_index("ix_ingestion_events_call", table_name="ingestion_events")
    op.drop_table("ingestion_events")
    op.drop_index("ix_calls_fixture", table_name="calls")
    op.drop_index("ix_calls_state", table_name="calls")
    op.drop_table("calls")
    op.execute("UPDATE system_metadata SET value = 'foundation_only' WHERE key = 'schema_purpose'")
