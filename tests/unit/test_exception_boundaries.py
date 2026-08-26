from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from apps.api.colacci_api import main as api_main
from apps.worker.colacci_worker import main as worker_main
from packages.contracts.review import (
    FailureClass,
    IngestionDisposition,
    IngestionResult,
    ProcessingState,
    SanitizedProcessingFailure,
    StructuredAnalysis,
)
from packages.database.repository import AttemptRecord, CallSummary
from packages.review.fixtures import FixtureAnalyzer, FixtureCallSource
from packages.review.pipeline import FixturePipeline
from packages.review.validation import ReviewValidationError
from scripts import (
    secret_scan,
    transcription_cli_preflight,
    transcription_live_preflight,
    unsafe_production_probe,
)


def _rejecting_settings(**_: object) -> None:
    raise ValueError("sensitive-startup-detail-must-not-appear")


@pytest.mark.parametrize(
    ("module", "service"),
    [
        (api_main, "api"),
        (worker_main, "worker"),
        (unsafe_production_probe, "production-guard-probe"),
    ],
)
def test_startup_rejection_remains_sanitized(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    module: Any,
    service: str,
) -> None:
    monkeypatch.setattr(module, "Settings", _rejecting_settings)
    with pytest.raises(SystemExit) as raised:
        module.main()
    assert raised.value.code == 78
    output = capsys.readouterr().out
    assert '"event":"startup_rejected"' in output
    assert f'"service":"{service}"' in output
    assert '"error_code":"unsafe_configuration"' in output
    assert "sensitive-startup-detail-must-not-appear" not in output


class MemoryRepository:
    def __init__(self) -> None:
        self.state = ProcessingState.RECEIVED
        self.failure: SanitizedProcessingFailure | None = None
        self.transcript_count = 0
        self.analysis_count = 0

    def ingest(self, event: Any, *, preferred_call_id: str | None = None) -> IngestionResult:
        del event, preferred_call_id
        return IngestionResult(
            call_id="candidate-call",
            event_id="candidate-event",
            disposition=IngestionDisposition.ACCEPTED,
        )

    def start_attempt(self, call_id: str, provenance: Any) -> AttemptRecord:
        assert call_id == "candidate-call"
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

    def fail(self, call_id: str, attempt_id: str, failure: SanitizedProcessingFailure) -> None:
        assert call_id and attempt_id
        self.failure = failure
        self.state = failure.terminal_state

    def call_summary(self, call_id: str) -> CallSummary:
        assert call_id == "candidate-call"
        return CallSummary(
            call_id=call_id,
            fixture_id="CL-FX-001",
            state=self.state,
            attempt_count=1,
            transcript_count=self.transcript_count,
            analysis_count=self.analysis_count,
        )


class RejectingAnalyzer(FixtureAnalyzer):
    def __init__(self, rejection: Exception) -> None:
        super().__init__()
        self.rejection = rejection

    def extract_facts(self, fixture_id: str, transcript: Any) -> Any:
        del fixture_id, transcript
        raise self.rejection


def _pydantic_rejection() -> ValidationError:
    try:
        StructuredAnalysis.model_validate({})
    except ValidationError as error:
        return error
    raise AssertionError("invalid structured analysis unexpectedly validated")


@pytest.mark.parametrize(
    "rejection",
    [
        ValueError("invalid value"),
        ReviewValidationError("invalid evidence"),
        _pydantic_rejection(),
    ],
)
def test_structured_output_rejection_is_terminal_and_classified(rejection: Exception) -> None:
    source = FixtureCallSource()
    repository = MemoryRepository()
    pipeline = FixturePipeline(
        cast(Any, repository),
        source=source,
        analyzer=RejectingAnalyzer(rejection),
    )
    outcome = pipeline.process(source.events("CL-FX-001")[0])
    assert outcome.terminal_state is ProcessingState.OUTPUT_VALIDATION_FAILED
    assert outcome.attempt_count == 1
    assert repository.failure is not None
    assert repository.failure.failure_class is FailureClass.INVALID_STRUCTURED_OUTPUT
    assert repository.failure.diagnostic_code == "structured_output_rejected"
    assert repository.failure.retryable is False


class UnreadableTextPath:
    name = "candidate.txt"
    suffix = ".txt"

    def read_text(self, *, encoding: str) -> str:
        assert encoding == "utf-8"
        raise OSError("content must remain unavailable")


def test_secret_scanner_fails_closed_without_disclosing_unreadable_content() -> None:
    assert secret_scan.scan_paths([cast(Path, UnreadableTextPath())]) == []


@pytest.mark.parametrize(
    "failure",
    [OSError("unavailable"), subprocess.TimeoutExpired(cmd="openai", timeout=3)],
)
def test_cli_preflight_process_failure_is_bounded(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    def reject(*_: object, **__: object) -> None:
        raise failure

    monkeypatch.setattr(transcription_cli_preflight.subprocess, "run", reject)
    assert transcription_cli_preflight._bounded_local_command(Path("/usr/bin/false"), ()) == (
        127,
        b"",
    )


def test_live_transcription_preflight_rejects_missing_generated_assets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        transcription_live_preflight,
        "MANIFEST_PATH",
        tmp_path / "missing-generated-manifest.json",
    )
    assets, failures = transcription_live_preflight._inspect_assets()
    assert assets == []
    assert failures == ["generated_media_inspection"]
