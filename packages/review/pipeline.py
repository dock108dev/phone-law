"""Facts-first deterministic fixture pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from pydantic import ValidationError

from packages.contracts.review import (
    SCHEMA_VERSION,
    FailureClass,
    IngestionDisposition,
    IngestionEvent,
    ProcessingState,
    Provenance,
    SanitizedProcessingFailure,
)
from packages.database.repository import ReviewRepository, opaque_id
from packages.review.fixtures import (
    FixtureAdapterError,
    FixtureAnalyzer,
    FixtureCallSource,
    FixtureTranscriber,
)
from packages.review.validation import ReviewValidationError, validate_analysis

PLAYBOOK_VERSION = "synthetic-draft-v1"


@dataclass(frozen=True)
class FixtureOutcome:
    fixture_id: str
    call_id: str
    disposition: IngestionDisposition
    terminal_state: ProcessingState
    attempt_count: int
    transcript_count: int
    analysis_count: int


class FixturePipeline:
    def __init__(
        self,
        repository: ReviewRepository,
        source: FixtureCallSource | None = None,
        transcriber: FixtureTranscriber | None = None,
        analyzer: FixtureAnalyzer | None = None,
    ) -> None:
        self.repository = repository
        self.source = source or FixtureCallSource()
        self.transcriber = transcriber or FixtureTranscriber(self.source.manifest)
        self.analyzer = analyzer or FixtureAnalyzer(self.source.manifest)

    def process(self, event: IngestionEvent) -> FixtureOutcome:
        ingestion = self.repository.ingest(event)
        if ingestion.disposition is not IngestionDisposition.ACCEPTED:
            summary = self.repository.call_summary(ingestion.call_id)
            return FixtureOutcome(
                fixture_id=event.fixture_id,
                call_id=ingestion.call_id,
                disposition=ingestion.disposition,
                terminal_state=summary.state,
                attempt_count=summary.attempt_count,
                transcript_count=summary.transcript_count,
                analysis_count=summary.analysis_count,
            )

        return self._run_attempts(event, ingestion.call_id, ingestion.disposition)

    def retry(self, event: IngestionEvent, call_id: str) -> FixtureOutcome:
        """Run an explicitly authorized new attempt for an existing synthetic call."""

        summary = self.repository.call_summary(call_id)
        if summary.fixture_id != event.fixture_id:
            raise ValueError("fixture retry target does not match the existing call")
        return self._run_attempts(event, call_id, IngestionDisposition.ACCEPTED)

    def _run_attempts(
        self,
        event: IngestionEvent,
        call_id: str,
        disposition: IngestionDisposition,
    ) -> FixtureOutcome:
        while True:
            attempt_id = opaque_id()
            provenance = Provenance(
                schema_version=cast(Any, SCHEMA_VERSION),
                call_source=event.call.source,
                source_event_id=event.call.source_event_id,
                source_call_id=event.call.source_call_id,
                transcript_adapter=self.transcriber.adapter_name,
                transcript_model_version=self.transcriber.model_version,
                analysis_adapter=self.analyzer.adapter_name,
                analysis_model_version=self.analyzer.model_version,
                prompt_version=self.analyzer.prompt_version,
                playbook_version=PLAYBOOK_VERSION,
                adapter_version=self.analyzer.adapter_version,
                generated_at=event.received_at,
                processing_attempt_id=attempt_id,
                environment="fixture",
            )
            attempt = self.repository.start_attempt(call_id, provenance)
            self.repository.advance(call_id, attempt.attempt_id, ProcessingState.VALIDATED)
            self.repository.advance(call_id, attempt.attempt_id, ProcessingState.QUEUED)
            self.repository.advance(call_id, attempt.attempt_id, ProcessingState.MEDIA_READY)
            self.repository.advance(call_id, attempt.attempt_id, ProcessingState.TRANSCRIBING)
            try:
                transcript = self.transcriber.transcribe(
                    event.call,
                    fixture_id=event.fixture_id,
                    call_id=call_id,
                    attempt_number=attempt.attempt_number,
                    provenance=provenance,
                )
            except FixtureAdapterError as exc:
                failure = SanitizedProcessingFailure(
                    failure_class=FailureClass(exc.failure_class),
                    terminal_state=cast(Any, ProcessingState(exc.terminal_state)),
                    diagnostic_code=exc.diagnostic_code,
                    retryable=exc.retryable,
                )
                self.repository.fail(call_id, attempt.attempt_id, failure)
                if exc.retryable:
                    continue
                break

            self.repository.store_transcript(transcript, attempt.attempt_id)
            self.repository.advance(call_id, attempt.attempt_id, ProcessingState.TRANSCRIBED)
            self.repository.advance(call_id, attempt.attempt_id, ProcessingState.EXTRACTING_FACTS)
            try:
                facts = self.analyzer.extract_facts(event.fixture_id, transcript)
                self.repository.advance(
                    call_id,
                    attempt.attempt_id,
                    ProcessingState.APPLYING_PLAYBOOK,
                )
                analysis = self.analyzer.apply_playbook(
                    event.fixture_id,
                    call_id=call_id,
                    facts=facts,
                    transcript=transcript,
                    provenance=provenance,
                )
                validate_analysis(
                    analysis,
                    transcript,
                    event.call.duration_seconds,
                    caller_identity_metadata_verified=bool(
                        event.call.metadata.get("caller_identity_verified", False)
                    ),
                )
                self.repository.store_analysis(analysis, attempt.attempt_id)
            # Preserve Python 3.13 parse compatibility for stale-image rejection diagnostics.
            except (ValidationError, ReviewValidationError, ValueError):  # fmt: skip
                failure = SanitizedProcessingFailure(
                    failure_class=FailureClass.INVALID_STRUCTURED_OUTPUT,
                    terminal_state=ProcessingState.OUTPUT_VALIDATION_FAILED,
                    diagnostic_code="structured_output_rejected",
                    retryable=False,
                )
                self.repository.fail(call_id, attempt.attempt_id, failure)
                break
            self.repository.advance(call_id, attempt.attempt_id, ProcessingState.ANALYZED)
            break

        summary = self.repository.call_summary(call_id)
        return FixtureOutcome(
            fixture_id=event.fixture_id,
            call_id=call_id,
            disposition=disposition,
            terminal_state=summary.state,
            attempt_count=summary.attempt_count,
            transcript_count=summary.transcript_count,
            analysis_count=summary.analysis_count,
        )

    def process_manifest(self) -> tuple[FixtureOutcome, ...]:
        return tuple(self.process(event) for event in self.source.events())
