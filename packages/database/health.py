"""Content-free database and schema readiness checks."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

EXPECTED_ALEMBIC_REVISION = "0003_synthetic_review_experience"


@dataclass(frozen=True)
class DatabaseReadiness:
    connected: bool
    migration_current: bool
    error_code: str | None = None

    @property
    def ready(self) -> bool:
        return self.connected and self.migration_current


def create_database_engine(database_url: str) -> Engine:
    return create_engine(database_url, pool_pre_ping=True, pool_recycle=300)


def database_readiness(engine: Engine) -> DatabaseReadiness:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
    except SQLAlchemyError:
        return DatabaseReadiness(
            connected=False,
            migration_current=False,
            error_code="database_unavailable_or_unmigrated",
        )

    current = revision == EXPECTED_ALEMBIC_REVISION
    return DatabaseReadiness(
        connected=True,
        migration_current=current,
        error_code=None if current else "migration_not_current",
    )
