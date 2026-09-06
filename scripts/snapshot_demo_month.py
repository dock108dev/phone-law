"""Hash persisted month rows without exporting their contents; exercise append-only reviews."""

from __future__ import annotations

import argparse
import hashlib
import json

import sqlalchemy as sa

from packages.config import Settings
from packages.contracts.report import DemoPrincipal, ReviewEventCreate
from packages.database.health import create_database_engine
from packages.database.review_experience import ReviewExperienceRepository
from packages.database.review_schema import analyses, calls, metadata


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--add-review", action="store_true")
    args = parser.parse_args()
    engine = create_database_engine(Settings(service_name="month-snapshot").sqlalchemy_database_url)
    try:
        if args.add_review:
            experience = ReviewExperienceRepository(engine)
            with engine.connect() as connection:
                analysis_id = connection.execute(
                    sa.select(analyses.c.id)
                    .join(calls, calls.c.id == analyses.c.call_id)
                    .where(calls.c.fixture_id == "CL-AM-20260715-09")
                ).scalar_one()
            if experience.review_history(analysis_id):
                raise SystemExit("review probe requires a fresh baseline; refusing to append twice")
            for note in (
                "Engineering review: missing caller identity remains unknown.",
                "Engineering follow-up: prior assessment retained; no real-world action implied.",
            ):
                experience.add_review(
                    analysis_id=analysis_id,
                    request=ReviewEventCreate.model_validate({"label": "missing", "note": note}),
                    principal=DemoPrincipal.model_validate_json(
                        '{"principal_id":"demo-reviewer","role":"reviewer","synthetic":true}'
                    ),
                )
        result = {}
        with engine.connect() as connection:
            for table in metadata.sorted_tables:
                rows = [dict(row) for row in connection.execute(sa.select(table)).mappings()]
                serialized = sorted(json.dumps(row, sort_keys=True, default=str) for row in rows)
                result[table.name] = {
                    "rows": len(rows),
                    "sha256": hashlib.sha256(json.dumps(serialized).encode()).hexdigest(),
                }
        print(json.dumps(result, sort_keys=True, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
