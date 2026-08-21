"""Idempotently seed the deterministic July 2026 transcript-only month."""

from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, time
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
    audit_events,
    calls,
    daily_reports,
    ingestion_events,
    review_events,
)
from packages.review.demo_month import DemoMonthCallSource, DemoMonthManifest
from packages.review.pipeline import FixturePipeline


def main() -> None:
    settings = Settings(service_name="demo-month-seed")
    parsed = urlsplit(settings.sqlalchemy_database_url.replace("postgresql+psycopg", "postgresql"))
    if not settings.synthetic_mode or parsed.path.endswith("_test"):
        raise SystemExit("demo month seeding requires the synthetic demo database")
    alembic = Config("alembic.ini")
    alembic.set_main_option("sqlalchemy.url", settings.sqlalchemy_database_url)
    command.upgrade(alembic, "head")
    engine = create_database_engine(settings.sqlalchemy_database_url)
    manifest = DemoMonthManifest()
    source = DemoMonthCallSource(manifest)
    try:
        repository = ReviewRepository(engine)
        playbook = PlaybookVersion.model_validate_json(
            Path("fixtures/playbooks/synthetic-draft-v1.json").read_text(encoding="utf-8")
        )
        repository.install_playbook(playbook.model_dump(mode="json"))
        pipeline = FixturePipeline(repository, source=source)  # type: ignore[arg-type]
        with engine.connect() as connection:
            existing = set(
                connection.execute(sa.select(ingestion_events.c.source_event_id)).scalars()
            )
        for event in source.events():
            if event.call.source_event_id not in existing:
                pipeline.process(event)
                existing.add(event.call.source_event_id)

        duplicate_entries = [
            item
            for item in manifest.received_entries()
            if "duplicate_delivery" in item["scenarios"]
        ]
        for entry in duplicate_entries:
            event = source.events(str(entry["fixture_id"]))[0]
            with engine.connect() as connection:
                count = int(
                    connection.execute(
                        sa.select(ingestion_events.c.duplicate_delivery_count).where(
                            ingestion_events.c.source_event_id == event.call.source_event_id
                        )
                    ).scalar_one()
                )
            if count == 0:
                pipeline.process(event)

        timezone = ZoneInfo("America/New_York")
        experience = ReviewExperienceRepository(engine)
        daily: list[dict[str, object]] = []
        for day_number in range(1, 32):
            business_date = date(2026, 7, day_number)
            expected = tuple(
                str(item["event"]["call"]["source_call_id"])
                for item in manifest.expected_entries(business_date)
            )
            report = experience.generate_report(
                business_date=business_date,
                cutoff_at=datetime.combine(business_date, time(18), tzinfo=timezone),
                expected_source_call_ids=expected,
            )
            daily.append(
                {
                    "business_date": str(business_date),
                    "status": report.completeness.status.value,
                    **report.completeness.reconciliation.model_dump(mode="json"),
                }
            )
        with engine.connect() as connection:
            month_calls = int(
                connection.execute(
                    sa.select(sa.func.count())
                    .select_from(calls)
                    .where(calls.c.fixture_id.like("CL-MONTH-202607-%"))
                ).scalar_one()
            )
            month_analyses = int(
                connection.execute(
                    sa.select(sa.func.count())
                    .select_from(analyses.join(calls, analyses.c.call_id == calls.c.id))
                    .where(calls.c.fixture_id.like("CL-MONTH-202607-%"))
                ).scalar_one()
            )
            report_versions = Counter(
                connection.execute(
                    sa.select(daily_reports.c.business_date).where(
                        daily_reports.c.business_date.between(date(2026, 7, 1), date(2026, 7, 31))
                    )
                ).scalars()
            )
            immutable_event_counts = {
                "review_events": int(
                    connection.execute(
                        sa.select(sa.func.count()).select_from(review_events)
                    ).scalar_one()
                ),
                "audit_events": int(
                    connection.execute(
                        sa.select(sa.func.count()).select_from(audit_events)
                    ).scalar_one()
                ),
            }
        output = {
            **manifest.summary(),
            "synthetic": True,
            "network_used": False,
            "external_requests": 0,
            "real_or_human_audio": 0,
            "client_data": 0,
            "migration_revision": "0006_local_operations",
            "persisted": {
                "received": month_calls,
                "analyzed": month_analyses,
                "report_dates": len(report_versions),
                "report_versions_per_date": sorted(set(report_versions.values())),
                **immutable_event_counts,
            },
            "daily": daily,
        }
        print(json.dumps(output, indent=2, sort_keys=True))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
