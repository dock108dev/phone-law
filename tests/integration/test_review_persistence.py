from __future__ import annotations

import json
from urllib.parse import urlsplit

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import DBAPIError

from packages.config import Settings
from packages.contracts.review import AnalysisAcceptanceState, StructuredAnalysis
from packages.database.repository import ReviewRepository
from packages.database.review_schema import analyses, calls, processing_attempts, transcripts
from packages.review.fixtures import FixtureCallSource
from packages.review.pipeline import FixturePipeline

pytestmark = pytest.mark.integration


@pytest.fixture
def migrated_engine() -> sa.Engine:
    settings = Settings(_env_file=None, app_profile="test")
    parsed = urlsplit(settings.sqlalchemy_database_url.replace("postgresql+psycopg", "postgresql"))
    assert parsed.path.endswith("_test")
    alembic = Config("alembic.ini")
    alembic.set_main_option("sqlalchemy.url", settings.sqlalchemy_database_url)
    command.downgrade(alembic, "base")
    command.upgrade(alembic, "0001_foundation")
    engine = create_engine(settings.sqlalchemy_database_url)
    assert set(inspect(engine).get_table_names()) == {"alembic_version", "system_metadata"}
    command.upgrade(alembic, "0002_synthetic_review_contracts")
    slice_one_tables = set(inspect(engine).get_table_names())
    assert "analyses" in slice_one_tables
    assert "daily_reports" not in slice_one_tables
    command.upgrade(alembic, "head")
    try:
        yield engine
    finally:
        engine.dispose()


def test_migration_constraints_downgrade_and_reupgrade(migrated_engine: sa.Engine) -> None:
    inspector = inspect(migrated_engine)
    call_constraints = {item["name"] for item in inspector.get_unique_constraints("calls")}
    event_constraints = {
        item["name"] for item in inspector.get_unique_constraints("ingestion_events")
    }
    attempt_constraints = {
        item["name"] for item in inspector.get_unique_constraints("processing_attempts")
    }
    assert "uq_calls_source_call" in call_constraints
    assert "uq_ingestion_events_source_event" in event_constraints
    assert "uq_attempts_call_number" in attempt_constraints

    settings = Settings(_env_file=None, app_profile="test")
    alembic = Config("alembic.ini")
    alembic.set_main_option("sqlalchemy.url", settings.sqlalchemy_database_url)
    command.downgrade(alembic, "0002_synthetic_review_contracts")
    slice_one_tables = set(inspect(migrated_engine).get_table_names())
    assert "analyses" in slice_one_tables
    assert "daily_reports" not in slice_one_tables
    command.upgrade(alembic, "head")
    assert "daily_reports" in inspect(migrated_engine).get_table_names()

    command.downgrade(alembic, "0001_foundation")
    assert set(inspect(migrated_engine).get_table_names()) == {"alembic_version", "system_metadata"}
    command.upgrade(alembic, "head")
    assert "analyses" in inspect(migrated_engine).get_table_names()


def test_idempotency_retry_failure_and_immutable_outputs(migrated_engine: sa.Engine) -> None:
    repository = ReviewRepository(migrated_engine)
    source = FixtureCallSource()
    pipeline = FixturePipeline(repository, source=source)

    fixture_002 = pipeline.process(source.events("CL-FX-002")[0])
    duplicate_event = pipeline.process(source.events("CL-FX-002")[0])
    duplicate_call = pipeline.process(source.events("CL-FX-009")[0])
    retry = pipeline.process(source.events("CL-FX-010")[0])
    permanent_failure = pipeline.process(source.events("CL-FX-011")[0])

    assert fixture_002.call_id == duplicate_event.call_id == duplicate_call.call_id
    assert duplicate_event.disposition.value == "duplicate_event"
    assert duplicate_call.disposition.value == "duplicate_call"
    assert duplicate_call.analysis_count == 1
    assert retry.attempt_count == 2
    assert permanent_failure.terminal_state.value == "AUDIO_INVALID"
    assert permanent_failure.transcript_count == permanent_failure.analysis_count == 0

    with migrated_engine.connect() as connection:
        retry_states = (
            connection.execute(
                sa.select(processing_attempts.c.state)
                .where(processing_attempts.c.call_id == retry.call_id)
                .order_by(processing_attempts.c.attempt_number)
            )
            .scalars()
            .all()
        )
        duplicate_count = connection.execute(
            sa.select(sa.func.count())
            .select_from(calls)
            .where(calls.c.source_call_id == "call-cl-fx-002")
        ).scalar_one()
    assert retry_states == ["TRANSCRIPTION_FAILED", "ANALYZED"]
    assert duplicate_count == 1

    payload = repository.accepted_analysis_payload(fixture_002.call_id)
    assert payload is not None
    payload["acceptance_state"] = "needs_review"
    needs_review = StructuredAnalysis.model_validate_json(json.dumps(payload))
    assert needs_review.acceptance_state is AnalysisAcceptanceState.NEEDS_REVIEW
    with pytest.raises(ValueError, match="only strictly accepted"):
        repository.store_analysis(needs_review, "unused-attempt-identifier")

    with pytest.raises(DBAPIError, match="immutable"), migrated_engine.begin() as connection:
        connection.execute(
            analyses.update()
            .where(analyses.c.call_id == fixture_002.call_id)
            .values(acceptance_state="accepted")
        )
    with pytest.raises(DBAPIError, match="immutable"), migrated_engine.begin() as connection:
        connection.execute(transcripts.delete().where(transcripts.c.call_id == fixture_002.call_id))
