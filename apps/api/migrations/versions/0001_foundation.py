"""Create the content-free foundation metadata table."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_foundation"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "system_metadata",
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("value", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.execute(
        sa.text(
            "INSERT INTO system_metadata (key, value) "
            "VALUES ('schema_purpose', 'foundation_only')"
        )
    )


def downgrade() -> None:
    op.drop_table("system_metadata")
