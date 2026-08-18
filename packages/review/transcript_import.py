"""Strict synthetic transcript-only import through the accepted review pipeline."""

from __future__ import annotations

import hashlib
import json
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import model_validator

from packages.contracts.review import (
    FailureClass,
    IngestionDisposition,
    IngestionEvent,
    ProcessingState,
    SanitizedProcessingFailure,
    StrictModel,
    Transcript,
)
from packages.database.repository import ReviewRepository
from packages.review.fixtures import FixtureAnalyzer
from packages.review.validation import ReviewValidationError, validate_analysis

TRANSCRIPT_ONLY_ARTIFACT_VERSION = "transcript-only-artifact-v1"
TRANSCRIPT_ONLY_PROVIDER_VERSION = "transcript-only-contract-v1"
TRANSCRIPT_ONLY_MAX_BYTES = 256 * 1024
SUPPORTED_ANALYSIS_FIXTURES = frozenset({"CL-FX-002"})


def transcript_only_identifier(kind: str, source_identifier: str) -> str:
    return hashlib.sha256(f"transcript-only-{kind}:{source_identifier}".encode()).hexdigest()[:32]


class TranscriptOnlyArtifact(StrictModel):
    artifact_version: Literal["transcript-only-artifact-v1"]
    source_identifier: str
    analysis_fixture_reference: str
    event: IngestionEvent
    transcript: Transcript

    @model_validator(mode="after")
    def enforce_synthetic_import_boundary(self) -> TranscriptOnlyArtifact:
        call = self.event.call
        provenance = self.transcript.provenance
        expected_call_id = transcript_only_identifier("call", self.source_identifier)
        expected_attempt_id = transcript_only_identifier("attempt", self.source_identifier)
        expected_transcript_id = transcript_only_identifier("transcript", self.source_identifier)
        if self.analysis_fixture_reference not in SUPPORTED_ANALYSIS_FIXTURES:
            raise ValueError("unsupported deterministic analysis fixture")
        if call.source.value != "transcript_only" or not call.synthetic:
            raise ValueError("transcript-only artifacts must use the synthetic source")
        if call.source_call_id != self.source_identifier:
            raise ValueError("source identifier must match the normalized call")
        if self.transcript.call_id != expected_call_id:
            raise ValueError("transcript call identifier is not safely derived")
        if self.transcript.transcript_id != expected_transcript_id:
            raise ValueError("transcript identifier is not safely derived")
        if provenance.processing_attempt_id != expected_attempt_id:
            raise ValueError("attempt identifier is not safely derived")
        if (
            provenance.call_source is not call.source
            or provenance.source_event_id != call.source_event_id
            or provenance.source_call_id != call.source_call_id
            or provenance.environment != "local_dev"
            or provenance.transcript_adapter != "transcript-only-import"
            or provenance.transcript_model_version != TRANSCRIPT_ONLY_ARTIFACT_VERSION
            or provenance.analysis_adapter != "fixture-analyzer"
            or provenance.analysis_model_version != "deterministic-analysis-v1"
            or provenance.prompt_version != "facts-first-prompt-v1"
            or provenance.playbook_version != "synthetic-draft-v1"
            or provenance.adapter_version != "transcript-only-import-v1"
        ):
            raise ValueError("transcript-only provenance is outside the accepted contract")
        transport = provenance.transcription_transport
        if (
            transport is None
            or transport.transport != "transcript_only"
            or transport.declared_contract_version != TRANSCRIPT_ONLY_ARTIFACT_VERSION
            or transport.observed_cli_version != "unavailable"
            or transport.model_id != "invented-local-transcript"
            or transport.requested_response_format != "contract-json"
            or transport.generated_asset_fingerprint is not None
            or transport.attempt_number != 1
            or transport.result_kind != "transcript_only"
        ):
            raise ValueError("transcript-only transport provenance is invalid")
        if (
            self.transcript.provider_response_version != TRANSCRIPT_ONLY_PROVIDER_VERSION
            or self.transcript.media_hash_reference is not None
            or self.transcript.language != call.language_hint
        ):
            raise ValueError("transcript-only language or media boundary is invalid")
        joined_text = " ".join(item.text for item in self.transcript.segments)
        if self.transcript.original_language_text != joined_text:
            raise ValueError("original language text must exactly match the imported segments")
        return self


def load_transcript_only_artifact(path: Path) -> TranscriptOnlyArtifact:
    """Validate the entire local artifact before creating database state."""

    if not path.is_absolute() or path.suffix.lower() != ".json":
        raise ValueError("transcript artifact must be an absolute JSON path")
    try:
        info = path.lstat()
    except OSError as exc:
        raise ValueError("transcript artifact is unavailable") from exc
    if not stat.S_ISREG(info.st_mode) or path.is_symlink():
        raise ValueError("transcript artifact must be a regular non-symlink file")
    if info.st_mode & 0o022:
        raise ValueError("transcript artifact must not be group or world writable")
    if info.st_size <= 0 or info.st_size > TRANSCRIPT_ONLY_MAX_BYTES:
        raise ValueError("transcript artifact size is outside the local boundary")
    try:
        payload = path.read_bytes()
        return TranscriptOnlyArtifact.model_validate_json(payload)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("transcript artifact failed strict validation") from exc


@dataclass(frozen=True)
class TranscriptOnlyOutcome:
    source_identifier: str
    call_id: str
    disposition: IngestionDisposition
    terminal_state: ProcessingState
    attempt_count: int
    transcript_count: int
    analysis_count: int


class TranscriptOnlyImporter:
    def __init__(
        self,
        repository: ReviewRepository,
        analyzer: FixtureAnalyzer | None = None,
    ) -> None:
        self.repository = repository
        self.analyzer = analyzer or FixtureAnalyzer()

    def process(self, artifact: TranscriptOnlyArtifact) -> TranscriptOnlyOutcome:
        ingestion = self.repository.ingest(
            artifact.event,
            preferred_call_id=artifact.transcript.call_id,
        )
        if ingestion.disposition is not IngestionDisposition.ACCEPTED:
            return self._outcome(artifact, ingestion.call_id, ingestion.disposition)

        call_id = ingestion.call_id
        provenance = artifact.transcript.provenance
        attempt = self.repository.start_attempt(call_id, provenance)
        self.repository.advance(call_id, attempt.attempt_id, ProcessingState.VALIDATED)
        self.repository.advance(call_id, attempt.attempt_id, ProcessingState.QUEUED)
        self.repository.advance(call_id, attempt.attempt_id, ProcessingState.MEDIA_READY)
        self.repository.advance(call_id, attempt.attempt_id, ProcessingState.TRANSCRIBING)
        self.repository.store_transcript(artifact.transcript, attempt.attempt_id)
        self.repository.advance(call_id, attempt.attempt_id, ProcessingState.TRANSCRIBED)
        self.repository.advance(call_id, attempt.attempt_id, ProcessingState.EXTRACTING_FACTS)
        try:
            facts = self.analyzer.extract_facts(
                artifact.analysis_fixture_reference,
                artifact.transcript,
            )
            self.repository.advance(call_id, attempt.attempt_id, ProcessingState.APPLYING_PLAYBOOK)
            analysis = self.analyzer.apply_playbook(
                artifact.analysis_fixture_reference,
                call_id=call_id,
                facts=facts,
                transcript=artifact.transcript,
                provenance=provenance,
            )
            analysis = analysis.model_copy(
                update={
                    "analysis_id": transcript_only_identifier(
                        "analysis", artifact.source_identifier
                    )
                }
            )
            validate_analysis(
                analysis,
                artifact.transcript,
                artifact.event.call.duration_seconds,
                caller_identity_metadata_verified=False,
            )
            self.repository.store_analysis(analysis, attempt.attempt_id)
        except (ReviewValidationError, ValueError) as exc:
            failure = SanitizedProcessingFailure(
                failure_class=FailureClass.INVALID_STRUCTURED_OUTPUT,
                terminal_state=ProcessingState.OUTPUT_VALIDATION_FAILED,
                diagnostic_code="transcript_only_output_rejected",
                retryable=False,
            )
            self.repository.fail(call_id, attempt.attempt_id, failure)
            raise ValueError("transcript-only downstream validation failed") from exc
        self.repository.advance(call_id, attempt.attempt_id, ProcessingState.ANALYZED)
        return self._outcome(artifact, call_id, ingestion.disposition)

    def _outcome(
        self,
        artifact: TranscriptOnlyArtifact,
        call_id: str,
        disposition: IngestionDisposition,
    ) -> TranscriptOnlyOutcome:
        summary = self.repository.call_summary(call_id)
        return TranscriptOnlyOutcome(
            source_identifier=artifact.source_identifier,
            call_id=call_id,
            disposition=disposition,
            terminal_state=summary.state,
            attempt_count=summary.attempt_count,
            transcript_count=summary.transcript_count,
            analysis_count=summary.analysis_count,
        )
