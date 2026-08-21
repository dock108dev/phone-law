from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, cast

import pytest

from packages.contracts.review import (
    IngestionDisposition,
    IngestionResult,
    ProcessingState,
    SanitizedProcessingFailure,
)
from packages.database.repository import AttemptRecord, CallSummary
from packages.review.transcript_import import (
    TRANSCRIPT_ONLY_MAX_BYTES,
    TranscriptOnlyImporter,
    load_transcript_only_artifact,
)

ARTIFACT_PATH = Path("fixtures/transcript-only/invented-call.json").resolve()


def test_invented_transcript_only_artifact_is_strict_and_synthetic() -> None:
    artifact = load_transcript_only_artifact(ARTIFACT_PATH)
    assert artifact.event.call.synthetic is True
    assert artifact.event.call.source.value == "transcript_only"
    assert artifact.transcript.language == "en"
    assert artifact.transcript.provenance.environment == "local_dev"
    assert artifact.transcript.provenance.transcription_transport is not None


@pytest.mark.parametrize(
    ("mutation", "value"),
    [
        (("artifact_version",), "unsupported-v2"),
        (("event", "call", "synthetic"), False),
        (("event", "call", "source"), "manual_upload"),
        (("event", "call", "media_reference"), "unsafe-media"),
        (("transcript", "language"), "es"),
        (("transcript", "provenance", "environment"), "production"),
        (
            ("transcript", "provenance", "transcription_transport", "result_kind"),
            "separately_authorized_live",
        ),
    ],
)
def test_unsupported_or_unsafe_transcript_artifacts_fail_before_import(
    tmp_path: Path,
    mutation: tuple[str, ...],
    value: object,
) -> None:
    payload = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    target = payload
    for key in mutation[:-1]:
        target = target[key]
    target[mutation[-1]] = value
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="strict validation"):
        load_transcript_only_artifact(path.resolve())


def test_malformed_oversized_writable_and_symlink_artifacts_are_rejected(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed.json"
    malformed.write_text("not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="strict validation"):
        load_transcript_only_artifact(malformed.resolve())

    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b"x" * (TRANSCRIPT_ONLY_MAX_BYTES + 1))
    with pytest.raises(ValueError, match="size"):
        load_transcript_only_artifact(oversized.resolve())

    writable = tmp_path / "writable.json"
    writable.write_bytes(ARTIFACT_PATH.read_bytes())
    os.chmod(writable, 0o666)  # noqa: S103 - deliberate unsafe-input rejection case
    with pytest.raises(ValueError, match="writable"):
        load_transcript_only_artifact(writable.resolve())

    link = tmp_path / "link.json"
    link.symlink_to(ARTIFACT_PATH)
    with pytest.raises(ValueError, match="non-symlink"):
        load_transcript_only_artifact(link)


class InMemoryReviewRepository:
    def __init__(self, *, duplicate: bool = False) -> None:
        self.duplicate = duplicate
        self.state = ProcessingState.ANALYZED if duplicate else ProcessingState.RECEIVED
        self.transcript_count = 1 if duplicate else 0
        self.analysis_count = 1 if duplicate else 0
        self.failure: SanitizedProcessingFailure | None = None

    def ingest(self, event: Any, *, preferred_call_id: str | None = None) -> IngestionResult:
        assert preferred_call_id is not None
        return IngestionResult(
            call_id=preferred_call_id,
            event_id="event-memory",
            disposition=(
                IngestionDisposition.DUPLICATE_EVENT
                if self.duplicate
                else IngestionDisposition.ACCEPTED
            ),
        )

    def start_attempt(self, call_id: str, provenance: Any) -> AttemptRecord:
        assert call_id
        return AttemptRecord(attempt_id=provenance.processing_attempt_id, attempt_number=1)

    def advance(self, call_id: str, attempt_id: str, target: ProcessingState) -> None:
        assert call_id and attempt_id
        self.state = target

    def store_transcript(self, transcript: Any, attempt_id: str) -> None:
        assert transcript and attempt_id
        self.transcript_count += 1

    def store_analysis(self, analysis: Any, attempt_id: str) -> None:
        assert analysis and attempt_id
        self.analysis_count += 1

    def fail(
        self,
        call_id: str,
        attempt_id: str,
        failure: SanitizedProcessingFailure,
    ) -> None:
        assert call_id and attempt_id
        self.failure = failure
        self.state = failure.terminal_state

    def call_summary(self, call_id: str) -> CallSummary:
        return CallSummary(
            call_id=call_id,
            fixture_id="CL-TX-001",
            state=self.state,
            attempt_count=1,
            transcript_count=self.transcript_count,
            analysis_count=self.analysis_count,
        )


def test_transcript_only_importer_processes_and_deduplicates_with_existing_contracts() -> None:
    artifact = load_transcript_only_artifact(ARTIFACT_PATH)
    repository = InMemoryReviewRepository()
    outcome = TranscriptOnlyImporter(cast(Any, repository)).process(artifact)
    assert outcome.disposition is IngestionDisposition.ACCEPTED
    assert outcome.terminal_state is ProcessingState.ANALYZED
    assert outcome.transcript_count == 1
    assert outcome.analysis_count == 1

    duplicate_repository = InMemoryReviewRepository(duplicate=True)
    duplicate = TranscriptOnlyImporter(cast(Any, duplicate_repository)).process(artifact)
    assert duplicate.disposition is IngestionDisposition.DUPLICATE_EVENT
    assert duplicate.terminal_state is ProcessingState.ANALYZED
    assert duplicate.analysis_count == 1


class RejectingAnalyzer:
    def extract_facts(self, fixture_id: str, transcript: Any) -> None:
        raise ValueError("deliberate deterministic rejection")


def test_transcript_only_importer_records_content_free_downstream_failure() -> None:
    artifact = load_transcript_only_artifact(ARTIFACT_PATH)
    repository = InMemoryReviewRepository()
    importer = TranscriptOnlyImporter(
        cast(Any, repository),
        analyzer=cast(Any, RejectingAnalyzer()),
    )
    with pytest.raises(ValueError, match="downstream validation failed"):
        importer.process(artifact)
    assert repository.failure is not None
    assert repository.failure.diagnostic_code == "transcript_only_output_rejected"
    assert repository.state is ProcessingState.OUTPUT_VALIDATION_FAILED
