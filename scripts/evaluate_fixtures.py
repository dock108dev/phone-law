"""Evaluate all deterministic fixtures and emit non-repository evidence."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from pydantic import ValidationError

from packages.config import Settings
from packages.contracts.review import (
    AnalysisAcceptanceState,
    Finding,
    PlaybookVersion,
    Priority,
    StructuredAnalysis,
    ValueState,
)
from packages.database.health import create_database_engine
from packages.database.repository import ReviewRepository
from packages.database.review_schema import calls, processing_attempts, transcripts
from packages.review.fixtures import FixtureCallSource, FixtureManifest
from packages.review.pipeline import FixtureOutcome, FixturePipeline
from packages.review.validation import (
    ReviewValidationError,
    acceptance_state_for,
    validate_analysis,
)

DEFAULT_REPORT_DIRECTORY = Path(tempfile.gettempdir()) / "colacci-law-fixtures"


@dataclass(frozen=True)
class FixtureReport:
    fixture_id: str
    disposition: str
    terminal_state: str
    attempt_count: int
    assertion_count: int
    status: str


def _assert_equal(actual: object, expected: object, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def _assert_specific(
    fixture_id: str, analysis: StructuredAnalysis, transcript_payload: dict[str, Any]
) -> None:
    segments = cast(list[dict[str, Any]], transcript_payload["segments"])
    if fixture_id == "CL-FX-002":
        commitment = analysis.facts.staff_commitments[0]
        _assert_equal(commitment.evidence[0].segment_id, "fx002-seg-4", "commitment evidence")
        _assert_equal(commitment.evidence[0].speaker.value, "staff", "commitment speaker")
    elif fixture_id == "CL-FX-003":
        _assert_equal(cast(str, transcript_payload["language"]), "es", "source language")
        if analysis.suggested_response_timing is not None:
            raise AssertionError("Spanish callback time was invented")
    elif fixture_id == "CL-FX-004":
        if not analysis.dissatisfaction_indicators[0].evidence:
            raise AssertionError("dissatisfaction finding lacks evidence")
    elif fixture_id == "CL-FX-006":
        _assert_equal(analysis.confidence.value, "low", "partial transcript confidence")
        if not analysis.facts.missing_context:
            raise AssertionError("partial transcript missing context is hidden")
    elif fixture_id == "CL-FX-007":
        if "unknown_participant" not in {str(item["speaker"]) for item in segments}:
            raise AssertionError("ambiguous participant was not retained")
    elif fixture_id == "CL-FX-008":
        _assert_equal(analysis.priority, Priority.LOW, "prompt injection priority")
    elif fixture_id == "CL-FX-012":
        if any(
            item.state is not ValueState.UNVERIFIED or item.is_deadline
            for item in analysis.facts.dates
        ):
            raise AssertionError("unconfirmed date became confirmed or a deadline")


def _verify_outcome(
    outcome: FixtureOutcome,
    expected: dict[str, Any],
    repository: ReviewRepository,
    transcript_payload: dict[str, Any] | None,
    expected_provenance: dict[str, str],
) -> FixtureReport:
    _assert_equal(outcome.disposition.value, expected["disposition"], "disposition")
    _assert_equal(outcome.terminal_state.value, expected["terminal_state"], "terminal state")
    _assert_equal(outcome.attempt_count, expected["attempt_count"], "attempt count")
    if outcome.fixture_id == "CL-FX-011":
        _assert_equal(outcome.transcript_count, 0, "permanent failure transcript count")
        _assert_equal(outcome.analysis_count, 0, "permanent failure analysis count")
    elif outcome.disposition.value == "accepted":
        _assert_equal(outcome.transcript_count, 1, "accepted transcript count")
        _assert_equal(outcome.analysis_count, 1, "accepted analysis count")
        payload = repository.accepted_analysis_payload(outcome.call_id)
        if payload is None or transcript_payload is None:
            raise AssertionError("accepted payload missing")
        analysis = StructuredAnalysis.model_validate_json(json.dumps(payload, ensure_ascii=False))
        _assert_equal(analysis.category.value, expected["category"], "analysis category")
        _assert_equal(analysis.priority.value, expected["priority"], "analysis priority")
        _assert_equal(analysis.summary, expected["summary"], "analysis summary")
        _assert_equal(
            analysis.acceptance_state,
            AnalysisAcceptanceState.ACCEPTED,
            "analysis acceptance",
        )
        actual_provenance = analysis.provenance.model_dump(mode="json")
        for key, value in expected_provenance.items():
            _assert_equal(actual_provenance[key], value, f"provenance {key}")
        _assert_specific(outcome.fixture_id, analysis, transcript_payload)
    return FixtureReport(
        fixture_id=outcome.fixture_id,
        disposition=outcome.disposition.value,
        terminal_state=outcome.terminal_state.value,
        attempt_count=outcome.attempt_count,
        assertion_count=int(expected["assertion_count"])
        + (
            len(expected_provenance)
            if outcome.disposition.value == "accepted" and outcome.analysis_count
            else 0
        ),
        status="pass",
    )


def _rejected_example(repository: ReviewRepository, call_id: str) -> dict[str, object]:
    payload = repository.accepted_analysis_payload(call_id)
    if payload is None:
        raise AssertionError("English accepted analysis is unavailable")
    candidate = dict(payload)
    candidate["priority"] = "high"
    candidate["acceptance_state"] = "accepted"
    candidate["findings"] = [
        Finding(
            finding_id="unsupported-high-finding",
            kind="unsupported_priority",
            statement="Unsupported high-priority candidate.",
            material=True,
            evidence=(),
        ).model_dump(mode="json")
    ]
    analysis = StructuredAnalysis.model_validate_json(json.dumps(candidate, ensure_ascii=False))
    with repository.engine.connect() as connection:
        transcript_raw = connection.execute(
            sa.select(transcripts.c.original_payload).where(transcripts.c.call_id == call_id)
        ).scalar_one()
        duration = float(
            connection.execute(
                sa.select(calls.c.normalized_payload).where(calls.c.id == call_id)
            ).scalar_one()["duration_seconds"]
        )
    from packages.contracts.review import Transcript

    transcript = Transcript.model_validate_json(json.dumps(transcript_raw, ensure_ascii=False))
    state = acceptance_state_for(analysis, transcript, duration)
    try:
        validate_analysis(analysis, transcript, duration)
    except ReviewValidationError as exc:
        return {
            "candidate_acceptance_state": state.value,
            "diagnostic_code": str(exc),
            "candidate_priority": "high",
            "validation_result": "rejected",
            "accepted_analysis_stored": False,
        }
    raise AssertionError("unsupported high-priority candidate was accepted")


def _reset_test_data(engine: sa.Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "TRUNCATE analyses, transcripts, processing_attempts, ingestion_events, calls, "
                "playbook_versions RESTART IDENTITY CASCADE"
            )
        )


def main() -> None:
    settings = Settings(service_name="fixture-evaluator")
    parsed = urlsplit(settings.sqlalchemy_database_url.replace("postgresql+psycopg", "postgresql"))
    if settings.app_profile.value != "test" or not parsed.path.endswith("_test"):
        raise SystemExit("fixture evaluation may run only with APP_PROFILE=test on *_test")
    alembic = Config("alembic.ini")
    alembic.set_main_option("sqlalchemy.url", settings.sqlalchemy_database_url)
    command.upgrade(alembic, "head")
    engine = create_database_engine(settings.sqlalchemy_database_url)
    report_directory = Path(os.environ.get("FIXTURE_REPORT_DIRECTORY", DEFAULT_REPORT_DIRECTORY))
    report_directory.mkdir(parents=True, exist_ok=True)
    try:
        _reset_test_data(engine)
        manifest = FixtureManifest()
        source = FixtureCallSource(manifest)
        repository = ReviewRepository(engine)
        playbook_path = Path("fixtures/playbooks/synthetic-draft-v1.json")
        playbook = PlaybookVersion.model_validate_json(playbook_path.read_text(encoding="utf-8"))
        repository.install_playbook(playbook.model_dump(mode="json"))
        pipeline = FixturePipeline(repository, source=source)
        reports: list[FixtureReport] = []
        call_ids: dict[str, str] = {}
        for event in source.events():
            outcome = pipeline.process(event)
            call_ids[event.fixture_id] = outcome.call_id
            entry = manifest.entry(event.fixture_id)
            expected = cast(dict[str, Any], entry["expected_analysis"])
            transcript_payload = cast(dict[str, Any] | None, entry.get("transcript"))
            reports.append(
                _verify_outcome(
                    outcome,
                    expected,
                    repository,
                    transcript_payload,
                    manifest.expected_provenance,
                )
            )

        # Same event delivery remains one call and one accepted output.
        duplicate_event = pipeline.process(source.events("CL-FX-002")[0])
        _assert_equal(duplicate_event.disposition.value, "duplicate_event", "duplicate event")
        _assert_equal(duplicate_event.attempt_count, 1, "duplicate event attempt count")
        _assert_equal(duplicate_event.analysis_count, 1, "duplicate event analysis count")

        with engine.connect() as connection:
            pair_call_count = connection.execute(
                sa.select(sa.func.count())
                .select_from(calls)
                .where(calls.c.source_call_id == "call-cl-fx-002")
            ).scalar_one()
            retry_states = (
                connection.execute(
                    sa.select(processing_attempts.c.state)
                    .where(processing_attempts.c.call_id == call_ids["CL-FX-010"])
                    .order_by(processing_attempts.c.attempt_number)
                )
                .scalars()
                .all()
            )
        _assert_equal(pair_call_count, 1, "duplicate source call count")
        _assert_equal(retry_states, ["TRANSCRIPTION_FAILED", "ANALYZED"], "retry history")

        english = repository.accepted_analysis_payload(call_ids["CL-FX-002"])
        spanish = repository.accepted_analysis_payload(call_ids["CL-FX-003"])
        if english is None or spanish is None:
            raise AssertionError("accepted examples unavailable")
        rejected = _rejected_example(repository, call_ids["CL-FX-001"])
        (report_directory / "accepted-english-analysis.json").write_text(
            json.dumps(english, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (report_directory / "accepted-spanish-analysis.json").write_text(
            json.dumps(spanish, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (report_directory / "rejected-invalid-analysis.json").write_text(
            json.dumps(rejected, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        output = {
            "manifest_version": manifest.version,
            "migration_revision": "0002_synthetic_review_contracts",
            "fixture_count": len(reports),
            "passed": len(reports),
            "failed": 0,
            "assertion_count": sum(item.assertion_count for item in reports) + 5,
            "network_used": False,
            "fixtures": [asdict(item) for item in reports],
            "global_invariants": {
                "identical_event_idempotent": True,
                "duplicate_source_call_count": int(pair_call_count),
                "retry_states": list(retry_states),
                "invalid_high_priority_rejected": True,
            },
        }
        report_path = report_directory / "report.json"
        report_path.write_text(
            json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(json.dumps(output, indent=2, sort_keys=True))
        print(f"fixture-report: {report_path}")
    except (AssertionError, ValidationError) as exc:
        failure_path = report_directory / "report.json"
        failure_path.write_text(
            json.dumps({"fixture_count": 12, "passed": 0, "failed": 1, "error": str(exc)}, indent=2)
            + "\n",
            encoding="utf-8",
        )
        raise SystemExit(f"fixture evaluation failed: {exc}") from exc
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
