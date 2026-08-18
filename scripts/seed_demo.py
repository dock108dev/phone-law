"""Idempotently seed the deterministic synthetic review demonstration."""

from __future__ import annotations

import json
from datetime import datetime, time
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from packages.config import Settings
from packages.contracts.review import PlaybookVersion
from packages.database.health import create_database_engine
from packages.database.repository import ReviewRepository
from packages.database.review_experience import ReviewExperienceRepository
from packages.database.review_schema import (
    analyses,
    calls,
    daily_report_items,
    daily_reports,
    ingestion_events,
    processing_attempts,
    review_events,
)
from packages.review.fixtures import FixtureCallSource
from packages.review.pipeline import FixturePipeline


def main() -> None:
    settings = Settings(service_name="demo-seed")
    parsed = urlsplit(settings.sqlalchemy_database_url.replace("postgresql+psycopg", "postgresql"))
    if not settings.synthetic_mode or parsed.path.endswith("_test"):
        raise SystemExit("demo seeding requires the synthetic demo database")

    alembic = Config("alembic.ini")
    alembic.set_main_option("sqlalchemy.url", settings.sqlalchemy_database_url)
    command.upgrade(alembic, "head")
    engine = create_database_engine(settings.sqlalchemy_database_url)
    try:
        source = FixtureCallSource()
        repository = ReviewRepository(engine)
        playbook = PlaybookVersion.model_validate_json(
            Path("fixtures/playbooks/synthetic-draft-v1.json").read_text(encoding="utf-8")
        )
        repository.install_playbook(playbook.model_dump(mode="json"))
        pipeline = FixturePipeline(repository, source=source)
        with engine.connect() as connection:
            existing_event_ids = set(
                connection.execute(sa.select(ingestion_events.c.source_event_id)).scalars().all()
            )
        for event in source.events():
            if event.call.source_event_id not in existing_event_ids:
                pipeline.process(event)
                existing_event_ids.add(event.call.source_event_id)

        # Preserve one intentional identical redelivery without inflating it on later seed runs.
        replay_event = source.events("CL-FX-002")[0]
        with engine.connect() as connection:
            replay_count = int(
                connection.execute(
                    sa.select(ingestion_events.c.duplicate_delivery_count).where(
                        ingestion_events.c.source_event_id == replay_event.call.source_event_id
                    )
                ).scalar_one()
            )
        if replay_count == 0:
            pipeline.process(replay_event)

        timezone = ZoneInfo("America/New_York")
        events = source.events()
        business_date = events[0].call.occurred_at.astimezone(timezone).date()
        cutoff_at = datetime.combine(business_date, time(hour=18), tzinfo=timezone)
        expected_source_calls = tuple(
            sorted(
                {
                    event.call.source_call_id
                    for event in events
                    if event.call.occurred_at.astimezone(timezone).date() == business_date
                }
            )
        )
        experience = ReviewExperienceRepository(engine)
        report = experience.generate_report(
            business_date=business_date,
            cutoff_at=cutoff_at,
            expected_source_call_ids=expected_source_calls,
        )
        with engine.connect() as connection:
            counts = {
                "calls": int(
                    connection.execute(sa.select(sa.func.count()).select_from(calls)).scalar_one()
                ),
                "attempts": int(
                    connection.execute(
                        sa.select(sa.func.count()).select_from(processing_attempts)
                    ).scalar_one()
                ),
                "analyses": int(
                    connection.execute(
                        sa.select(sa.func.count()).select_from(analyses)
                    ).scalar_one()
                ),
                "reports": int(
                    connection.execute(
                        sa.select(sa.func.count()).select_from(daily_reports)
                    ).scalar_one()
                ),
                "report_items": int(
                    connection.execute(
                        sa.select(sa.func.count()).select_from(daily_report_items)
                    ).scalar_one()
                ),
                "review_events": int(
                    connection.execute(
                        sa.select(sa.func.count()).select_from(review_events)
                    ).scalar_one()
                ),
            }
        output = {
            "synthetic": True,
            "network_used": False,
            "migration_revision": "0005_manual_upload_local",
            "business_date": str(business_date),
            "report_id": report.report_id,
            "report_version": report.version,
            "report_status": report.completeness.status.value,
            "reconciliation": report.completeness.reconciliation.model_dump(mode="json"),
            "database_counts": counts,
        }
        print(json.dumps(output, indent=2, sort_keys=True))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
