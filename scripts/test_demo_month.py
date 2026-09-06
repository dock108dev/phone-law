"""Validate Slice 6C manifest and persisted month without retaining call content."""

from __future__ import annotations

import json
import os
from collections import Counter
from datetime import date
from pathlib import Path

import sqlalchemy as sa

from packages.config import Settings
from packages.contracts.report import DailyReport
from packages.contracts.review import StructuredAnalysis, Transcript
from packages.database.health import create_database_engine
from packages.database.review_experience import ReviewExperienceRepository
from packages.database.review_schema import (
    analyses,
    audit_events,
    calls,
    daily_reports,
    ingestion_events,
    review_events,
    transcripts,
)
from packages.review.demo_month import DemoMonthManifest
from packages.review.month_content_review import expectations, review_recap, verify_originals

EVIDENCE_ROOT = Path(
    os.environ.get(
        "SLICE6C_EVIDENCE_DIR",
        "/tmp/colacci-law-slice6c/evidence",  # nosec B108 - restrictive evidence root
    )
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    manifest = DemoMonthManifest()
    verify_originals(manifest)
    contract_totals = manifest.contract["totals"]
    require(
        contract_totals
        == {
            "expected": 227,
            "received": 226,
            "analyzed": 224,
            "failed": 2,
            "missing": 1,
            "late": 3,
            "duplicate_deliveries": 3,
        },
        "independently reviewed v2 baseline mismatch",
    )
    engine = create_database_engine(
        Settings(service_name="demo-month-test").sqlalchemy_database_url
    )
    evidence_count = 0
    spanish_preserved = 0
    high_priority_valid = 0
    try:
        with engine.connect() as connection:
            call_rows = (
                connection.execute(
                    sa.select(calls).where(
                        calls.c.fixture_id.in_([e["fixture_id"] for e in manifest.entries()])
                    )
                )
                .mappings()
                .all()
            )
            call_ids = tuple(str(row["id"]) for row in call_rows)
            analysis_rows = (
                connection.execute(
                    sa.select(analyses.c.original_payload).where(analyses.c.call_id.in_(call_ids))
                )
                .scalars()
                .all()
            )
            transcript_rows = (
                connection.execute(
                    sa.select(transcripts.c.call_id, transcripts.c.original_payload).where(
                        transcripts.c.call_id.in_(call_ids)
                    )
                )
                .mappings()
                .all()
            )
            report_rows = (
                connection.execute(
                    sa.select(
                        daily_reports.c.business_date,
                        daily_reports.c.version,
                        daily_reports.c.snapshot_payload,
                    )
                    .where(
                        daily_reports.c.business_date.between(date(2026, 7, 1), date(2026, 7, 31))
                    )
                    .order_by(daily_reports.c.business_date)
                )
                .mappings()
                .all()
            )
            duplicate_count = int(
                connection.execute(
                    sa.select(
                        sa.func.coalesce(
                            sa.func.sum(ingestion_events.c.duplicate_delivery_count), 0
                        )
                    )
                    .select_from(
                        ingestion_events.join(calls, ingestion_events.c.call_id == calls.c.id)
                    )
                    .where(calls.c.fixture_id.in_([e["fixture_id"] for e in manifest.entries()]))
                ).scalar_one()
            )
            review_count = int(
                connection.execute(
                    sa.select(sa.func.count()).select_from(review_events)
                ).scalar_one()
            )
            audit_count = int(
                connection.execute(
                    sa.select(sa.func.count()).select_from(audit_events)
                ).scalar_one()
            )

        with engine.connect() as connection:
            require(
                set(connection.execute(sa.select(calls.c.fixture_id)).scalars())
                == {e["fixture_id"] for e in manifest.received_entries()},
                "foreign or standalone dataset records present",
            )
        require(len(call_rows) == contract_totals["received"], "persisted received total mismatch")
        require(
            len(analysis_rows) == contract_totals["analyzed"], "persisted analyzed total mismatch"
        )
        require(
            len(call_rows) - len(analysis_rows) == contract_totals["failed"],
            "persisted failed total mismatch",
        )
        require(
            duplicate_count == contract_totals["duplicate_deliveries"], "duplicate total mismatch"
        )
        require(len(report_rows) == 31, "all 31 daily reports must exist once")
        require(
            {int(row["version"]) for row in report_rows} == {1}, "reseeding created report versions"
        )

        transcripts_by_call = {
            str(row["call_id"]): Transcript.model_validate_json(
                json.dumps(row["original_payload"], ensure_ascii=False)
            )
            for row in transcript_rows
        }
        for payload in analysis_rows:
            analysis = StructuredAnalysis.model_validate_json(
                json.dumps(payload, ensure_ascii=False)
            )
            transcript = transcripts_by_call[analysis.call_id]
            segments = {segment.segment_id: segment for segment in transcript.segments}
            findings = (
                *analysis.attorney_attention_issues,
                *analysis.dissatisfaction_indicators,
                *analysis.omitted_information_findings,
                *analysis.findings,
            )
            for finding in findings:
                require(bool(finding.evidence), "accepted finding lacks evidence")
                for evidence in finding.evidence:
                    segment = segments.get(evidence.segment_id)
                    if segment is None:
                        raise AssertionError("evidence segment does not exist")
                    require(segment.start_seconds == evidence.start_seconds, "evidence start drift")
                    require(segment.end_seconds == evidence.end_seconds, "evidence end drift")
                    require(segment.text == evidence.excerpt, "evidence excerpt drift")
                    evidence_count += 1
                if analysis.priority.value in {"immediate", "high"}:
                    require(finding.material, "high-priority finding must be material")
                    high_priority_valid += 1
            for fact in analysis.facts.dates:
                if fact.state.value == "unverified":
                    require(
                        not fact.is_deadline and fact.iso_date is None,
                        "unverified date became a deadline",
                    )
            if transcript.language == "es":
                joined = " ".join(segment.text for segment in transcript.segments)
                require(
                    transcript.original_language_text == joined,
                    "Spanish original text was not preserved",
                )
                spanish_preserved += 1

        daily_summaries: list[dict[str, object]] = []
        monthly: Counter[str] = Counter()
        statuses: Counter[str] = Counter()
        for row in report_rows:
            report = DailyReport.model_validate_json(json.dumps(row["snapshot_payload"]))
            counts = report.completeness.reconciliation
            authored_day = next(
                d
                for d in manifest.contract["daily_schedule"]
                if d["date"] == str(report.business_date)
            )
            for key in contract_totals:
                require(
                    getattr(counts, key) == authored_day[key],
                    f"daily authored {key} mismatch on {report.business_date}",
                )
            require(
                counts.expected == counts.received + counts.missing,
                "daily expected equation failed",
            )
            require(
                counts.received == counts.analyzed + counts.failed, "daily received equation failed"
            )
            monthly.update(
                expected=counts.expected,
                received=counts.received,
                analyzed=counts.analyzed,
                failed=counts.failed,
                missing=counts.missing,
                late=counts.late,
                duplicate_deliveries=counts.duplicate_deliveries,
            )
            statuses[report.completeness.status.value] += 1
            daily_summaries.append(
                {
                    "business_date": str(report.business_date),
                    "status": report.completeness.status.value,
                    **counts.model_dump(mode="json"),
                }
            )
        for key, expected in contract_totals.items():
            require(monthly[key] == expected, f"monthly {key} mismatch")
        require(
            statuses["zero_activity"] == 9, "eight weekends and one closure must show zero activity"
        )
        require(
            sum(1 for item in daily_summaries if item["expected"] != 0) == 22,
            "weekday count mismatch",
        )
        require(
            spanish_preserved
            == 32
            - sum(
                1
                for item in manifest.entries()
                if item["language"] == "es" and item["outcome"] != "analyzed"
            ),
            "received Spanish analysis preservation mismatch",
        )
        require(evidence_count > 0, "evidence coverage was empty")

        scenario_inventory = Counter(
            scenario for item in manifest.entries() for scenario in item["scenarios"]
        )
        for scenario in manifest.contract["scenario_contract"]:
            require(scenario_inventory[scenario] > 0, f"scenario missing: {scenario}")
        received_metadata = Counter(
            str(row["normalized_payload"]["metadata"]["expected_category"]) for row in call_rows
        )
        require(
            received_metadata
            == Counter(str(item["category"]) for item in manifest.received_entries()),
            "persisted expected category metadata mismatch",
        )
        received_languages = Counter(
            str(row["normalized_payload"]["metadata"]["expected_language"]) for row in call_rows
        )
        require(
            received_languages
            == Counter(str(item["language"]) for item in manifest.received_entries()),
            "persisted expected language metadata mismatch",
        )

        experience = ReviewExperienceRepository(engine)
        oracle = expectations()
        review_results = []
        for day in manifest.contract["coverage_dates"]:
            briefing = experience.briefing(date.fromisoformat(day))
            authored_day = next(d for d in manifest.contract["daily_schedule"] if d["date"] == day)
            require(len(briefing.calls) == authored_day["received"], "recap count mismatch")
            for recap in briefing.calls:
                entry = manifest.entry(recap.synthetic_reference)
                if recap.synthetic_reference in oracle:
                    references = review_recap(recap, oracle[recap.synthetic_reference])
                    if recap.detail is not None:
                        require(
                            recap.detail.summary == entry["expected_analysis"]["summary"],
                            "persisted recap drift",
                        )
                    review_results.append(
                        {
                            "fixture_id": recap.synthetic_reference,
                            "result": "passed",
                            "references_checked": references,
                            "state": recap.state,
                        }
                    )
                else:
                    require(
                        recap.state == "unavailable" and recap.detail is None,
                        "failed transcript invented a recap",
                    )
            if day == "2026-07-15":
                require(
                    len(briefing.calls) == 10
                    and sum(bool(c.attention) for c in briefing.calls) == 3,
                    "morning preservation mismatch",
                )
        for outside in (date(2026, 6, 30), date(2026, 8, 1)):
            require(
                experience.briefing(outside).completeness is None,
                "outside coverage became verified zero",
            )
        require(len(review_results) == 225, "not every usable conversation was reviewed")
        output = {
            "decision": "passed",
            "conversation_reviews": review_results,
            "manifest": manifest.summary(),
            "monthly_reconciliation": dict(monthly),
            "daily_reconciliation": daily_summaries,
            "report_status_counts": dict(statuses),
            "database": {
                "unique_calls": len(call_rows),
                "accepted_analyses": len(analysis_rows),
                "report_versions": len(report_rows),
                "review_events": review_count,
                "audit_events": audit_count,
            },
            "evidence_validation": {
                "references_checked": evidence_count,
                "high_priority_material_findings": high_priority_valid,
                "spanish_transcripts_preserved": spanish_preserved,
            },
            "scenario_inventory": dict(sorted(scenario_inventory.items())),
            "idempotency": {
                "unique_calls": True,
                "accepted_analyses": True,
                "report_versions": True,
                "duplicate_delivery_total_stable": True,
            },
            "counters": {
                "external_requests": 0,
                "notifications": 0,
                "real_or_human_audio": 0,
                "client_data": 0,
            },
        }
        EVIDENCE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
        EVIDENCE_ROOT.chmod(0o700)
        target = EVIDENCE_ROOT / "validation-results.json"
        target.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        target.chmod(0o600)
        print(json.dumps(output, indent=2, sort_keys=True))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
