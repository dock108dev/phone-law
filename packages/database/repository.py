"""Transactional persistence for synthetic review records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.dialects.postgresql import insert

from packages.contracts.review import (
    AnalysisAcceptanceState,
    IngestionDisposition,
    IngestionEvent,
    IngestionResult,
    ProcessingState,
    Provenance,
    SanitizedProcessingFailure,
    StructuredAnalysis,
    Transcript,
)
from packages.database.review_schema import (
    analyses,
    calls,
    ingestion_events,
    playbook_versions,
    processing_attempts,
    transcripts,
)
from packages.review.state_machine import start_explicit_retry, transition


def opaque_id() -> str:
    return uuid4().hex


@dataclass(frozen=True)
class AttemptRecord:
    attempt_id: str
    attempt_number: int


@dataclass(frozen=True)
class CallSummary:
    call_id: str
    fixture_id: str
    state: ProcessingState
    attempt_count: int
    transcript_count: int
    analysis_count: int


class ReviewRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def ingest(
        self, event: IngestionEvent, *, preferred_call_id: str | None = None
    ) -> IngestionResult:
        call = event.call
        payload = event.model_dump(mode="json")
        with self.engine.begin() as connection:
            existing_event = (
                connection.execute(
                    sa.select(ingestion_events.c.id, ingestion_events.c.call_id).where(
                        ingestion_events.c.source == call.source.value,
                        ingestion_events.c.source_event_id == call.source_event_id,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if existing_event:
                connection.execute(
                    ingestion_events.update()
                    .where(ingestion_events.c.id == existing_event["id"])
                    .values(
                        duplicate_delivery_count=ingestion_events.c.duplicate_delivery_count + 1,
                        disposition=IngestionDisposition.DUPLICATE_EVENT.value,
                    )
                )
                return IngestionResult(
                    call_id=existing_event["call_id"],
                    event_id=existing_event["id"],
                    disposition=IngestionDisposition.DUPLICATE_EVENT,
                )

            existing_call_id = connection.execute(
                sa.select(calls.c.id).where(
                    calls.c.source == call.source.value,
                    calls.c.source_call_id == call.source_call_id,
                )
            ).scalar_one_or_none()
            event_id = opaque_id()
            if existing_call_id:
                connection.execute(
                    ingestion_events.insert().values(
                        id=event_id,
                        call_id=existing_call_id,
                        source=call.source.value,
                        source_event_id=call.source_event_id,
                        fixture_id=event.fixture_id,
                        disposition=IngestionDisposition.DUPLICATE_CALL.value,
                        duplicate_delivery_count=0,
                        event_payload=payload,
                        received_at=event.received_at,
                    )
                )
                return IngestionResult(
                    call_id=existing_call_id,
                    event_id=event_id,
                    disposition=IngestionDisposition.DUPLICATE_CALL,
                )

            call_id = preferred_call_id or opaque_id()
            connection.execute(
                calls.insert().values(
                    id=call_id,
                    fixture_id=event.fixture_id,
                    source=call.source.value,
                    source_call_id=call.source_call_id,
                    state=ProcessingState.RECEIVED.value,
                    is_synthetic=call.synthetic,
                    occurred_at=call.occurred_at,
                    normalized_payload=call.model_dump(mode="json"),
                    created_at=event.received_at,
                )
            )
            connection.execute(
                ingestion_events.insert().values(
                    id=event_id,
                    call_id=call_id,
                    source=call.source.value,
                    source_event_id=call.source_event_id,
                    fixture_id=event.fixture_id,
                    disposition=IngestionDisposition.ACCEPTED.value,
                    duplicate_delivery_count=0,
                    event_payload=payload,
                    received_at=event.received_at,
                )
            )
        return IngestionResult(
            call_id=call_id,
            event_id=event_id,
            disposition=IngestionDisposition.ACCEPTED,
        )

    def start_attempt(self, call_id: str, provenance: Provenance) -> AttemptRecord:
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            state_value = connection.execute(
                sa.select(calls.c.state).where(calls.c.id == call_id).with_for_update()
            ).scalar_one()
            current = ProcessingState(state_value)
            highest = connection.execute(
                sa.select(sa.func.max(processing_attempts.c.attempt_number)).where(
                    processing_attempts.c.call_id == call_id
                )
            ).scalar_one()
            attempt_number = int(highest or 0) + 1
            if attempt_number > 1:
                start_explicit_retry(current)
                connection.execute(
                    calls.update()
                    .where(calls.c.id == call_id)
                    .values(state=ProcessingState.RECEIVED.value)
                )
            elif current is not ProcessingState.RECEIVED:
                raise ValueError("initial attempt requires RECEIVED state")
            attempt_id = provenance.processing_attempt_id
            connection.execute(
                processing_attempts.insert().values(
                    id=attempt_id,
                    call_id=call_id,
                    attempt_number=attempt_number,
                    state=ProcessingState.RECEIVED.value,
                    provenance_payload=provenance.model_dump(mode="json"),
                    started_at=now,
                )
            )
        return AttemptRecord(attempt_id=attempt_id, attempt_number=attempt_number)

    def advance(self, call_id: str, attempt_id: str, target: ProcessingState) -> None:
        with self.engine.begin() as connection:
            current = ProcessingState(
                connection.execute(
                    sa.select(processing_attempts.c.state).where(
                        processing_attempts.c.id == attempt_id
                    )
                ).scalar_one()
            )
            transition(current, target)
            values: dict[str, object] = {"state": target.value}
            if target is ProcessingState.ANALYZED:
                values["completed_at"] = datetime.now(UTC)
            connection.execute(
                processing_attempts.update()
                .where(processing_attempts.c.id == attempt_id)
                .values(**values)
            )
            connection.execute(
                calls.update().where(calls.c.id == call_id).values(state=target.value)
            )

    def fail(
        self,
        call_id: str,
        attempt_id: str,
        failure: SanitizedProcessingFailure,
    ) -> None:
        with self.engine.begin() as connection:
            current = ProcessingState(
                connection.execute(
                    sa.select(processing_attempts.c.state).where(
                        processing_attempts.c.id == attempt_id
                    )
                ).scalar_one()
            )
            transition(current, ProcessingState(failure.terminal_state))
            connection.execute(
                processing_attempts.update()
                .where(processing_attempts.c.id == attempt_id)
                .values(
                    state=failure.terminal_state.value,
                    failure_class=failure.failure_class.value,
                    diagnostic_code=failure.diagnostic_code,
                    retryable=failure.retryable,
                    completed_at=datetime.now(UTC),
                )
            )
            connection.execute(
                calls.update()
                .where(calls.c.id == call_id)
                .values(state=failure.terminal_state.value)
            )

    def store_transcript(self, transcript: Transcript, attempt_id: str) -> None:
        payload = transcript.model_dump(mode="json")
        provenance = transcript.provenance
        with self.engine.begin() as connection:
            connection.execute(
                transcripts.insert().values(
                    id=transcript.transcript_id,
                    call_id=transcript.call_id,
                    attempt_id=attempt_id,
                    language=transcript.language,
                    original_payload=payload,
                    schema_version=provenance.schema_version,
                    adapter_version=provenance.adapter_version,
                    model_version=provenance.transcript_model_version,
                    created_at=provenance.generated_at,
                )
            )

    def store_analysis(self, analysis: StructuredAnalysis, attempt_id: str) -> None:
        if analysis.acceptance_state is not AnalysisAcceptanceState.ACCEPTED:
            raise ValueError("only strictly accepted analyses may be persisted")
        payload = analysis.model_dump(mode="json")
        provenance = analysis.provenance
        with self.engine.begin() as connection:
            connection.execute(
                analyses.insert().values(
                    id=analysis.analysis_id,
                    call_id=analysis.call_id,
                    attempt_id=attempt_id,
                    acceptance_state=analysis.acceptance_state.value,
                    original_payload=payload,
                    schema_version=provenance.schema_version,
                    prompt_version=provenance.prompt_version,
                    playbook_version=provenance.playbook_version,
                    adapter_version=provenance.adapter_version,
                    model_version=provenance.analysis_model_version,
                    created_at=provenance.generated_at,
                )
            )

    def install_playbook(self, payload: dict[str, object]) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                insert(playbook_versions)
                .values(
                    id=str(payload["playbook_id"]),
                    version=str(payload["version"]),
                    status=str(payload["status"]),
                    is_synthetic=bool(payload["synthetic"]),
                    structured_payload=payload,
                    created_at=datetime.now(UTC),
                )
                .on_conflict_do_nothing(index_elements=["version"])
            )

    def call_summary(self, call_id: str) -> CallSummary:
        with self.engine.connect() as connection:
            row = connection.execute(
                sa.select(calls.c.fixture_id, calls.c.state).where(calls.c.id == call_id)
            ).one()
            attempt_count = connection.execute(
                sa.select(sa.func.count())
                .select_from(processing_attempts)
                .where(processing_attempts.c.call_id == call_id)
            ).scalar_one()
            transcript_count = connection.execute(
                sa.select(sa.func.count())
                .select_from(transcripts)
                .where(transcripts.c.call_id == call_id)
            ).scalar_one()
            analysis_count = connection.execute(
                sa.select(sa.func.count())
                .select_from(analyses)
                .where(analyses.c.call_id == call_id)
            ).scalar_one()
        return CallSummary(
            call_id=call_id,
            fixture_id=str(row.fixture_id),
            state=ProcessingState(row.state),
            attempt_count=int(attempt_count),
            transcript_count=int(transcript_count),
            analysis_count=int(analysis_count),
        )

    def accepted_analysis_payload(self, call_id: str) -> dict[str, object] | None:
        with self.engine.connect() as connection:
            payload = connection.execute(
                sa.select(analyses.c.original_payload).where(analyses.c.call_id == call_id)
            ).scalar_one_or_none()
        return payload if isinstance(payload, dict) else None
