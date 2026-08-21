"""Create the immutable synthetic report and human review experience."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_synthetic_review_experience"
down_revision: str | None = "0002_synthetic_review_contracts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "playbook_versions", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "playbook_versions", sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_table(
        "daily_reports",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("business_date", sa.Date, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("input_fingerprint", sa.String(64), nullable=False),
        sa.Column("cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot_payload", postgresql.JSONB, nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("business_date", "version", name="uq_daily_reports_date_version"),
        sa.UniqueConstraint(
            "business_date", "input_fingerprint", name="uq_daily_reports_inputs"
        ),
    )
    op.create_index("ix_daily_reports_date", "daily_reports", ["business_date", "version"])
    op.create_table(
        "daily_report_items",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "report_id", sa.String(32), sa.ForeignKey("daily_reports.id"), nullable=False
        ),
        sa.Column("call_id", sa.String(32), sa.ForeignKey("calls.id"), nullable=False),
        sa.Column(
            "analysis_id", sa.String(32), sa.ForeignKey("analyses.id"), nullable=True
        ),
        sa.Column("section", sa.String(64), nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("item_payload", postgresql.JSONB, nullable=False),
        sa.UniqueConstraint(
            "report_id", "section", "position", name="uq_report_items_position"
        ),
    )
    op.create_index("ix_report_items_call", "daily_report_items", ["call_id"])
    op.create_table(
        "review_events",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "analysis_id", sa.String(32), sa.ForeignKey("analyses.id"), nullable=False
        ),
        sa.Column("finding_id", sa.String(128), nullable=True),
        sa.Column("label", sa.String(32), nullable=False),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("principal_id", sa.String(64), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_review_events_analysis", "review_events", ["analysis_id", "created_at"])
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("principal_id", sa.String(64), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("target_type", sa.String(64), nullable=False),
        sa.Column("target_id", sa.String(128), nullable=False),
        sa.Column("result", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_events_created", "audit_events", ["created_at"])
    for table in ("daily_reports", "daily_report_items", "review_events", "audit_events"):
        op.execute(
            f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION prevent_immutable_review_record_change()"
        )
    op.execute(
        """
        CREATE FUNCTION preserve_playbook_content() RETURNS trigger AS $$
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
        "CREATE TRIGGER immutable_playbook_content BEFORE UPDATE OR DELETE ON playbook_versions "
        "FOR EACH ROW EXECUTE FUNCTION preserve_playbook_content()"
    )
    op.execute(
        "UPDATE system_metadata SET value = 'synthetic_review_experience' "
        "WHERE key = 'schema_purpose'"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER immutable_playbook_content ON playbook_versions")
    op.execute("DROP FUNCTION preserve_playbook_content")
    for table in ("audit_events", "review_events", "daily_report_items", "daily_reports"):
        op.execute(f"DROP TRIGGER immutable_{table} ON {table}")
    op.drop_index("ix_audit_events_created", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_review_events_analysis", table_name="review_events")
    op.drop_table("review_events")
    op.drop_index("ix_report_items_call", table_name="daily_report_items")
    op.drop_table("daily_report_items")
    op.drop_index("ix_daily_reports_date", table_name="daily_reports")
    op.drop_table("daily_reports")
    op.drop_column("playbook_versions", "retired_at")
    op.drop_column("playbook_versions", "published_at")
    op.execute(
        "UPDATE system_metadata SET value = 'synthetic_review_contracts' "
        "WHERE key = 'schema_purpose'"
    )
