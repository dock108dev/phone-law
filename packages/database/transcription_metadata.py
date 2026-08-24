"""Content-free persistence for media and provider-attempt provenance."""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy import Engine

from packages.contracts.media import (
    MediaDeletionEvent,
    MediaInspectionResult,
    MediaLifecycleEvent,
    TranscriptionErrorClassification,
    TranscriptionResponseMetadata,
)
from packages.database.review_schema import (
    media_artifacts,
    media_lifecycle_events,
    transcription_provider_attempts,
)


class TranscriptionMetadataRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def store_artifact(self, inspection: MediaInspectionResult, *, call_id: str | None) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                media_artifacts.insert().values(
                    id=inspection.artifact_id,
                    call_id=call_id,
                    is_synthetic=True,
                    content_hash_reference=inspection.hash_reference,
                    media_format=inspection.media_format.value,
                    byte_size=inspection.byte_size,
                    duration_seconds=inspection.duration_seconds,
                    channel_count=inspection.channel_count,
                    sample_rate_hz=inspection.sample_rate_hz,
                    lifecycle_state="INSPECTED",
                    created_at=inspection.inspected_at,
                    deleted_at=None,
                )
            )

    def store_lifecycle(self, event: MediaLifecycleEvent | MediaDeletionEvent) -> None:
        deletion_confirmed = (
            event.deletion_confirmed if isinstance(event, MediaDeletionEvent) else None
        )
        error_class = (
            event.error_class.value
            if isinstance(event, MediaDeletionEvent) and event.error_class is not None
            else None
        )
        with self.engine.begin() as connection:
            connection.execute(
                media_lifecycle_events.insert().values(
                    id=event.event_id,
                    artifact_id=event.artifact_id,
                    state=event.state.value,
                    deletion_confirmed=deletion_confirmed,
                    error_class=error_class,
                    occurred_at=event.occurred_at,
                )
            )

    def store_attempt(
        self,
        *,
        attempt_id: str,
        artifact_id: str,
        call_id: str | None,
        adapter_version: str,
        model_id: str,
        duration_ms: float,
        response: TranscriptionResponseMetadata | None = None,
        failure: TranscriptionErrorClassification | None = None,
    ) -> None:
        if (response is None) == (failure is None):
            raise ValueError("exactly one provider attempt outcome is required")
        outcome = response if response is not None else failure
        if outcome is None:
            raise AssertionError("provider attempt outcome validation failed")
        attempt_number = outcome.attempt_number
        usage = response.usage if response else None
        with self.engine.begin() as connection:
            connection.execute(
                transcription_provider_attempts.insert().values(
                    id=attempt_id,
                    artifact_id=artifact_id,
                    call_id=call_id,
                    attempt_number=attempt_number,
                    adapter_version=adapter_version,
                    model_id=model_id,
                    provider_response_version=(
                        response.provider_response_version if response else None
                    ),
                    timestamp_availability=(
                        response.timestamp_availability.value if response else None
                    ),
                    diarization_availability=(
                        response.diarization_availability.value if response else None
                    ),
                    safe_error_class=failure.error_class.value if failure else None,
                    retryable=failure.retryable if failure else False,
                    duration_ms=duration_ms,
                    input_tokens=usage.input_tokens if usage else None,
                    output_tokens=usage.output_tokens if usage else None,
                    usage_duration_seconds=usage.duration_seconds if usage else None,
                    created_at=datetime.now(UTC),
                )
            )

    def counts(self) -> dict[str, int]:
        with self.engine.connect() as connection:
            return {
                "media_artifacts": int(
                    connection.execute(
                        sa.select(sa.func.count()).select_from(media_artifacts)
                    ).scalar_one()
                ),
                "media_lifecycle_events": int(
                    connection.execute(
                        sa.select(sa.func.count()).select_from(media_lifecycle_events)
                    ).scalar_one()
                ),
                "transcription_provider_attempts": int(
                    connection.execute(
                        sa.select(sa.func.count()).select_from(transcription_provider_attempts)
                    ).scalar_one()
                ),
            }
