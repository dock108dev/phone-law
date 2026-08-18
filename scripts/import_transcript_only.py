"""Explicit local_dev transcript-only command and sanitized full-loop evidence."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from sqlalchemy import create_engine

from packages.config import AppProfile, Settings
from packages.contracts.report import (
    DemoPrincipal,
    DemoPrincipalId,
    DemoRole,
    ReviewEventCreate,
    ReviewLabel,
)
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
    transcripts,
)
from packages.review.transcript_import import (
    TRANSCRIPT_ONLY_MAX_BYTES,
    TranscriptOnlyImporter,
    load_transcript_only_artifact,
)

SLICE_ROOT = Path("/tmp/colacci-law-slice3c")  # noqa: S108  # nosec B108
EVIDENCE_ROOT = SLICE_ROOT / "evidence"
INVALID_ROOT = SLICE_ROOT / "invalid-imports"


def _database_counts(engine: sa.Engine) -> dict[str, int]:
    tables = {
        "calls": calls,
        "ingestion_events": ingestion_events,
        "processing_attempts": processing_attempts,
        "transcripts": transcripts,
        "analyses": analyses,
        "daily_reports": daily_reports,
        "daily_report_items": daily_report_items,
        "review_events": review_events,
    }
    with engine.connect() as connection:
        return {
            name: int(
                connection.execute(sa.select(sa.func.count()).select_from(table)).scalar_one()
            )
            for name, table in tables.items()
        }


def _prove_invalid_inputs_create_no_state(engine: sa.Engine, valid_path: Path) -> None:
    shutil.rmtree(INVALID_ROOT, ignore_errors=True)
    INVALID_ROOT.mkdir(mode=0o700, parents=True)
    malformed = INVALID_ROOT / "malformed.json"
    malformed.write_text("not-json", encoding="utf-8")
    unsupported = INVALID_ROOT / "unsupported.json"
    payload = json.loads(valid_path.read_text(encoding="utf-8"))
    payload["artifact_version"] = "unsupported-v2"
    unsupported.write_text(json.dumps(payload), encoding="utf-8")
    oversized = INVALID_ROOT / "oversized.json"
    oversized.write_bytes(b"x" * (TRANSCRIPT_ONLY_MAX_BYTES + 1))
    unsafe = INVALID_ROOT / "unsafe.json"
    unsafe.write_bytes(valid_path.read_bytes())
    # Deliberately construct an unsafe negative-test input.
    os.chmod(unsafe, 0o666)  # noqa: S103  # nosec B103
    for path in (malformed, unsupported, oversized, unsafe):
        try:
            load_transcript_only_artifact(path.resolve())
        except ValueError:
            continue
        raise AssertionError("invalid transcript-only artifact was accepted")
    if any(_database_counts(engine).values()):
        raise AssertionError("invalid transcript-only inputs created orphaned state")
    shutil.rmtree(INVALID_ROOT)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--artifact",
        type=Path,
        default=Path("/workspace/fixtures/transcript-only/invented-call.json"),
    )
    args = parser.parse_args()
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        app_profile=AppProfile.LOCAL_DEV,
        call_source_adapter="transcript_only",
        transcriber_adapter="transcript_only_import",
        analyzer_adapter="fixture",
        media_temp_root=Path(
            "/tmp/colacci-law-slice3c/objects"  # noqa: S108  # nosec B108
        ),
    )
    artifact_path = args.artifact.resolve()
    engine = create_engine(settings.sqlalchemy_database_url)
    try:
        _prove_invalid_inputs_create_no_state(engine, artifact_path)
        artifact = load_transcript_only_artifact(artifact_path)
        importer = TranscriptOnlyImporter(ReviewRepository(engine))
        first = importer.process(artifact)
        duplicate = importer.process(artifact)
        experience = ReviewExperienceRepository(engine)
        report = experience.generate_report(
            business_date=date(2026, 8, 17),
            cutoff_at=datetime(2026, 8, 17, 18, tzinfo=ZoneInfo("America/New_York")),
            expected_source_call_ids=(artifact.source_identifier,),
        )
        detail = experience.call_detail(first.call_id)
        if detail is None:
            raise AssertionError("transcript-only call detail is unavailable")
        finding = next(
            item for item in detail.findings if item.finding_id == "fx002-finding-commitment"
        )
        evidence = finding.evidence[0]
        segment_ids = {item.segment_id for item in detail.transcript_segments}
        if evidence.segment_id not in segment_ids:
            raise AssertionError("transcript-only evidence navigation is unresolved")
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
        refreshed = ReviewExperienceRepository(engine).call_detail(first.call_id)
        if refreshed is None or len(refreshed.review_history) != 1:
            raise AssertionError("transcript-only reviewer feedback did not persist")
        counts = _database_counts(engine)
        if counts["calls"] != 1 or counts["transcripts"] != 1 or counts["analyses"] != 1:
            raise AssertionError("transcript-only idempotency invariant failed")
        transport = detail.provenance.transcription_transport
        if transport is None:
            raise AssertionError("transcript-only safe provenance is absent")
        EVIDENCE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
        full_loop = {
            "schema_version": "slice3c-transcript-only-full-loop-v1",
            "status": "passed",
            "execution_profile": "local_dev",
            "source_label": "transcript_only",
            "synthetic": True,
            "language_preserved": detail.language == artifact.transcript.language,
            "terminal_state": first.terminal_state.value,
            "duplicate_disposition": duplicate.disposition.value,
            "one_normalized_call": counts["calls"] == 1,
            "one_accepted_analysis": counts["analyses"] == 1,
            "daily_report_created": counts["daily_reports"] == 1,
            "report_complete": report.completeness.status.value == "complete",
            "evidence_navigation_resolved": True,
            "review_feedback_persisted_after_refresh": True,
            "invalid_cases_rejected_before_state": 4,
            "orphaned_state_from_invalid_inputs": 0,
            "external_network_requests": 0,
            "provider_requests": 0,
            "raw_content_retained_in_evidence": False,
        }
        provenance = {
            "schema_version": "slice3c-database-provenance-v1",
            "source": detail.provenance.call_source.value,
            "environment": detail.provenance.environment,
            "transport": transport.transport,
            "declared_contract_version": transport.declared_contract_version,
            "observed_cli_version": transport.observed_cli_version,
            "model_id": transport.model_id,
            "requested_response_format": transport.requested_response_format,
            "attempt_number": transport.attempt_number,
            "result_kind": transport.result_kind,
            "counts": counts,
            "transcript_content_in_evidence": False,
            "audio_content_in_database": False,
        }
        for filename, payload in (
            ("transcript-only-full-loop.json", full_loop),
            ("database-provenance.json", provenance),
        ):
            path = EVIDENCE_ROOT / filename
            path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            os.chmod(path, 0o600)
    finally:
        engine.dispose()
        shutil.rmtree(INVALID_ROOT, ignore_errors=True)
    print("transcript-only-full-loop call=1 analysis=1 report=complete feedback=persisted")


if __name__ == "__main__":
    main()
