"""Prepare a separately reset technical database with interrupted fixture processing.

Engineering fault injection only. Existing authored month content is never altered.
"""

from __future__ import annotations

from contextlib import suppress
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import sqlalchemy as sa

from packages.config import Settings
from packages.contracts.review import PlaybookVersion, SanitizedProcessingFailure
from packages.database.health import create_database_engine
from packages.database.repository import ReviewRepository
from packages.database.review_experience import ReviewExperienceRepository
from packages.database.review_schema import calls
from packages.review.fixtures import FixtureAdapterError, FixtureCallSource, FixtureTranscriber
from packages.review.pipeline import FixturePipeline


def main() -> None:
    settings = Settings(service_name="recovery-probe")
    if not settings.synthetic_mode:
        raise SystemExit("Recovery probe requires synthetic mode")
    engine = create_database_engine(settings.sqlalchemy_database_url)
    try:
        with engine.connect() as connection:
            if connection.execute(sa.select(sa.func.count()).select_from(calls)).scalar_one():
                raise SystemExit("Recovery probe requires an empty disposable database")
        repository = ReviewRepository(engine)
        repository.install_playbook(
            PlaybookVersion.model_validate_json(
                Path("fixtures/playbooks/synthetic-draft-v1.json").read_text()
            ).model_dump(mode="json")
        )
        source = FixtureCallSource()
        original_fail = repository.fail

        def interrupt_after_failure(
            call_id: str, attempt_id: str, failure: SanitizedProcessingFailure
        ) -> None:
            original_fail(call_id, attempt_id, failure)
            raise InterruptedError("engineering_worker_interrupted_after_persisted_failure")

        for fixture in ("CL-FX-010",):
            with (
                patch.object(repository, "fail", side_effect=interrupt_after_failure),
                patch.object(
                    FixtureTranscriber,
                    "transcribe",
                    side_effect=FixtureAdapterError(
                        failure_class="transcriber_unavailable",
                        terminal_state="TRANSCRIPTION_FAILED",
                        diagnostic_code="engineering_interrupted_transcription",
                        retryable=True,
                    ),
                ),
                suppress(InterruptedError),
            ):
                FixturePipeline(repository, source=source).process(source.events(fixture)[0])
        FixturePipeline(repository, source=source).process(source.events("CL-FX-011")[0])
        experience = ReviewExperienceRepository(engine)
        experience.generate_report(
            business_date=date(2026, 8, 17),
            cutoff_at=datetime(2026, 8, 17, 18, tzinfo=ZoneInfo("America/New_York")),
            expected_source_call_ids=tuple(
                source.events(fixture)[0].call.source_call_id
                for fixture in ("CL-FX-010", "CL-FX-011", "CL-FX-001")
            ),
        )
        print("technical_recovery_probe received=2 analyzed=0 failed=2 missing=1")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
