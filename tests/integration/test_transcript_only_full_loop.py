from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine

from packages.config import Settings
from packages.contracts.report import (
    DemoPrincipal,
    DemoPrincipalId,
    DemoRole,
    ReviewEventCreate,
    ReviewLabel,
)
from packages.database.repository import ReviewRepository
from packages.database.review_experience import ReviewExperienceRepository
from packages.database.review_schema import analyses, calls, ingestion_events, transcripts
from packages.review.transcript_import import (
    TranscriptOnlyImporter,
    load_transcript_only_artifact,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def transcript_only_engine() -> sa.Engine:
    settings = Settings(_env_file=None, app_profile="test")
    parsed = urlsplit(settings.sqlalchemy_database_url.replace("postgresql+psycopg", "postgresql"))
    assert parsed.path.endswith("_test")
    alembic = Config("alembic.ini")
    alembic.set_main_option("sqlalchemy.url", settings.sqlalchemy_database_url)
    command.downgrade(alembic, "base")
    command.upgrade(alembic, "head")
    engine = create_engine(settings.sqlalchemy_database_url)
    try:
        yield engine
    finally:
        engine.dispose()


def test_transcript_only_import_reaches_report_evidence_and_persistent_feedback(
    transcript_only_engine: sa.Engine,
) -> None:
    artifact = load_transcript_only_artifact(
        Path("fixtures/transcript-only/invented-call.json").resolve()
    )
    importer = TranscriptOnlyImporter(ReviewRepository(transcript_only_engine))
    first = importer.process(artifact)
    duplicate = importer.process(artifact)
    assert first.terminal_state.value == "ANALYZED"
    assert first.transcript_count == first.analysis_count == 1
    assert duplicate.disposition.value == "duplicate_event"
    assert duplicate.attempt_count == duplicate.transcript_count == duplicate.analysis_count == 1

    experience = ReviewExperienceRepository(transcript_only_engine)
    report = experience.generate_report(
        business_date=date(2026, 8, 17),
        cutoff_at=datetime(2026, 8, 17, 18, tzinfo=ZoneInfo("America/New_York")),
        expected_source_call_ids=(artifact.source_identifier,),
    )
    assert report.completeness.status.value == "complete"
    assert report.completeness.reconciliation.model_dump() == {
        "expected": 1,
        "received": 1,
        "duplicate_deliveries": 1,
        "analyzed": 1,
        "failed": 0,
        "missing": 0,
        "late": 0,
    }
    detail = experience.call_detail(first.call_id)
    assert detail is not None
    finding = next(
        item for item in detail.findings if item.finding_id == "fx002-finding-commitment"
    )
    evidence = finding.evidence[0]
    segment = next(
        item for item in detail.transcript_segments if item.segment_id == evidence.segment_id
    )
    assert segment.start_seconds == evidence.start_seconds
    assert segment.end_seconds == evidence.end_seconds
    assert detail.provenance.call_source.value == "transcript_only"
    assert detail.provenance.transcription_transport is not None
    assert detail.provenance.transcription_transport.result_kind == "transcript_only"

    principal = DemoPrincipal(
        principal_id=DemoPrincipalId.REVIEWER,
        role=DemoRole.REVIEWER,
        synthetic=True,
    )
    experience.add_review(
        analysis_id=detail.analysis_id,
        request=ReviewEventCreate(
            label=ReviewLabel.CORRECT,
            finding_id=finding.finding_id,
        ),
        principal=principal,
    )
    refreshed = ReviewExperienceRepository(transcript_only_engine).call_detail(first.call_id)
    assert refreshed is not None
    assert [item.label.value for item in refreshed.review_history] == ["correct"]

    with transcript_only_engine.connect() as connection:
        assert connection.execute(sa.select(sa.func.count()).select_from(calls)).scalar_one() == 1
        assert (
            connection.execute(sa.select(sa.func.count()).select_from(transcripts)).scalar_one()
            == 1
        )
        assert (
            connection.execute(sa.select(sa.func.count()).select_from(analyses)).scalar_one() == 1
        )
        assert (
            connection.execute(
                sa.select(sa.func.count()).select_from(ingestion_events)
            ).scalar_one()
            == 1
        )
        source = connection.execute(sa.select(calls.c.source)).scalar_one()
    assert source == "transcript_only"
