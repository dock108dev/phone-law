"""Production-shaped OpenAI file-transcription adapter with no live Slice 3A factory."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic, sleep
from typing import Any, Protocol, cast

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    RateLimitError,
)
from pydantic import BaseModel, ValidationError

from packages.config import Settings
from packages.contracts.media import (
    DiarizationAvailability,
    MediaErrorClass,
    MediaInspectionResult,
    ProviderSpeakerLabel,
    TemporaryObjectReference,
    TranscriptionErrorClassification,
    TranscriptionRequestMetadata,
    TranscriptionResponseMetadata,
    TranscriptionUsageMetadata,
)
from packages.contracts.media import (
    TimestampAvailability as MediaTimestampAvailability,
)
from packages.contracts.review import (
    DiarizationStatus,
    NormalizedCall,
    Provenance,
    Speaker,
    SpeakerIdentity,
    TimestampAvailability,
    Transcript,
    TranscriptSegment,
    TranscriptValidationState,
    ValueState,
)


class TranscriptionCreate(Protocol):
    def create(self, **kwargs: Any) -> object: ...


class AudioResource(Protocol):
    transcriptions: TranscriptionCreate


class InjectedOpenAIClient(Protocol):
    audio: AudioResource


class MediaResolver(Protocol):
    def resolve_media(
        self, media_reference: str
    ) -> tuple[TemporaryObjectReference, MediaInspectionResult, object]: ...


@dataclass(frozen=True)
class ProviderAttemptRecord:
    attempt_number: int
    duration_ms: float
    error: TranscriptionErrorClassification | None


class TranscriptionAdapterError(RuntimeError):
    def __init__(
        self,
        classification: TranscriptionErrorClassification,
        attempts: tuple[ProviderAttemptRecord, ...],
    ) -> None:
        super().__init__(classification.error_class.value)
        self.classification = classification
        self.attempts = attempts


class LiveTranscriptionBlockedError(RuntimeError):
    """Slice 3A hard stop: a live client cannot be constructed or executed."""


class OpenAITranscriber:
    adapter_name = "openai-transcriber-candidate"
    adapter_version = "openai-transcriber-candidate-v1"

    def __init__(
        self,
        *,
        client: InjectedOpenAIClient,
        media_resolver: MediaResolver,
        settings: Settings,
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
        jitter: Callable[[], float] = lambda: 0.0,
        attempt_recorder: Callable[[ProviderAttemptRecord], None] | None = None,
    ) -> None:
        if not settings.synthetic_mode:
            raise LiveTranscriptionBlockedError("candidate_adapter_offline_profiles_only")
        if settings.live_transcription_enabled or settings.live_transcription_authorized:
            raise LiveTranscriptionBlockedError("slice3b_not_implemented")
        self.client = client
        self.media_resolver = media_resolver
        self.settings = settings
        self.clock = clock
        self.sleeper = sleeper
        self.jitter = jitter
        self.attempt_recorder = attempt_recorder or (lambda _: None)
        self.model_version = settings.transcription_model_id
        self.request_metadata: list[TranscriptionRequestMetadata] = []
        self.response_metadata: TranscriptionResponseMetadata | None = None

    def transcribe(
        self,
        call: NormalizedCall,
        *,
        fixture_id: str,
        call_id: str,
        attempt_number: int,
        provenance: Provenance,
    ) -> Transcript:
        del fixture_id, attempt_number
        if not call.synthetic or call.media_reference is None:
            raise self._invalid_configuration(call_id)
        reference, inspection, raw_path = self.media_resolver.resolve_media(call.media_reference)
        if reference.artifact_id != inspection.artifact_id:
            raise self._invalid_configuration(call_id)
        if (
            inspection.byte_size > self.settings.media_max_bytes
            or inspection.duration_seconds > self.settings.media_max_duration_seconds
        ):
            raise self._invalid_configuration(call_id)

        attempts: list[ProviderAttemptRecord] = []
        for provider_attempt in range(1, 4):
            request_metadata = TranscriptionRequestMetadata(
                call_id=call_id,
                attempt_number=provider_attempt,
                artifact_id=inspection.artifact_id,
                media_hash_reference=inspection.hash_reference,
                adapter_version=self.adapter_version,
                model_id=self.settings.transcription_model_id,
                fallback_model_id=self.settings.transcription_fallback_model_id,
                response_format="diarized_json",
                chunking_strategy=("auto" if inspection.duration_seconds > 30 else None),
                timeout_seconds=self.settings.transcription_timeout_seconds,
                byte_size=inspection.byte_size,
                duration_seconds=inspection.duration_seconds,
            )
            self.request_metadata.append(request_metadata)
            started = self.clock()
            try:
                with cast(Any, raw_path).open("rb") as media_file:
                    kwargs: dict[str, Any] = {
                        "file": (
                            f"{reference.object_id}.wav",
                            media_file,
                            inspection.content_type.value,
                        ),
                        "model": self.settings.transcription_model_id,
                        "response_format": "diarized_json",
                        "timeout": self.settings.transcription_timeout_seconds,
                    }
                    if request_metadata.chunking_strategy is not None:
                        kwargs["chunking_strategy"] = request_metadata.chunking_strategy
                    response = self.client.audio.transcriptions.create(**kwargs)
                transcript, response_metadata = self._convert_response(
                    response,
                    call_id=call_id,
                    attempt_number=provider_attempt,
                    inspection=inspection,
                    provenance=provenance,
                )
            except Exception as exc:
                classification = self._classify_exception(exc, provider_attempt)
                duration_ms = max(0.0, (self.clock() - started) * 1000)
                record = ProviderAttemptRecord(provider_attempt, duration_ms, classification)
                attempts.append(record)
                self.attempt_recorder(record)
                if not classification.retryable or provider_attempt >= 3:
                    raise TranscriptionAdapterError(classification, tuple(attempts)) from exc
                self.sleeper(self._retry_delay(classification, provider_attempt))
                continue

            duration_ms = max(0.0, (self.clock() - started) * 1000)
            record = ProviderAttemptRecord(provider_attempt, duration_ms, None)
            attempts.append(record)
            self.attempt_recorder(record)
            self.response_metadata = response_metadata
            return transcript
        raise AssertionError("provider retry loop exited without a terminal result")

    def _convert_response(
        self,
        response: object,
        *,
        call_id: str,
        attempt_number: int,
        inspection: MediaInspectionResult,
        provenance: Provenance,
    ) -> tuple[Transcript, TranscriptionResponseMetadata]:
        payload = self._response_payload(response)
        text = payload.get("text")
        language = payload.get("language")
        if not isinstance(text, str) or not text.strip() or language not in {"en", "es"}:
            raise ValueError(MediaErrorClass.TRANSCRIPTION_RESPONSE_INVALID.value)
        response_version = payload.get("response_version", "openai-diarized-json-v1")
        if not isinstance(response_version, str) or not response_version:
            raise ValueError(MediaErrorClass.TRANSCRIPTION_RESPONSE_INVALID.value)
        usage = self._usage(payload.get("usage"))
        raw_segments = payload.get("segments")
        fallback = (
            payload.get("diarization") == "unavailable"
            or payload.get("model") == self.settings.transcription_fallback_model_id
        )
        if raw_segments is None:
            if not fallback:
                raise ValueError(MediaErrorClass.TRANSCRIPTION_RESPONSE_INVALID.value)
            transcript = Transcript(
                transcript_id=self._transcript_id(call_id, inspection.hash_reference),
                call_id=call_id,
                language=cast(Any, language),
                diarization_status=DiarizationStatus.UNAVAILABLE,
                original_language_text=text,
                timestamp_availability=TimestampAvailability.UNAVAILABLE,
                provider_response_version=response_version,
                media_hash_reference=inspection.hash_reference,
                validation_state=TranscriptValidationState.REQUIRES_HUMAN_REVIEW,
                segments=(),
                provenance=provenance,
            )
            metadata = TranscriptionResponseMetadata(
                call_id=call_id,
                attempt_number=attempt_number,
                model_id=self.settings.transcription_fallback_model_id,
                provider_response_version=response_version,
                language=cast(Any, language),
                timestamp_availability=MediaTimestampAvailability.UNAVAILABLE,
                diarization_availability=DiarizationAvailability.UNAVAILABLE,
                usage=usage,
            )
            return transcript, metadata
        if fallback or not isinstance(raw_segments, list) or not raw_segments:
            raise ValueError(MediaErrorClass.TRANSCRIPTION_RESPONSE_INVALID.value)

        segments: list[TranscriptSegment] = []
        labels: dict[str, ProviderSpeakerLabel] = {}
        previous_end = -1.0
        for index, raw in enumerate(raw_segments):
            if not isinstance(raw, dict):
                raise ValueError(MediaErrorClass.TRANSCRIPTION_RESPONSE_INVALID.value)
            segment_text = raw.get("text")
            speaker_label = raw.get("speaker")
            start = raw.get("start")
            end = raw.get("end")
            if (
                not isinstance(segment_text, str)
                or not segment_text.strip()
                or not isinstance(speaker_label, str)
                or not speaker_label
                or isinstance(start, bool)
                or isinstance(end, bool)
                or not isinstance(start, int | float)
                or not isinstance(end, int | float)
            ):
                raise ValueError(MediaErrorClass.TRANSCRIPTION_RESPONSE_INVALID.value)
            start_value = float(start)
            end_value = float(end)
            if start_value < 0 or start_value >= end_value or start_value < previous_end:
                raise ValueError(MediaErrorClass.TRANSCRIPTION_RESPONSE_INVALID.value)
            if end_value > inspection.duration_seconds + 0.5:
                raise ValueError(MediaErrorClass.TRANSCRIPTION_RESPONSE_INVALID.value)
            previous_end = end_value
            try:
                label = ProviderSpeakerLabel(raw_label=speaker_label)
            except ValidationError as exc:
                raise ValueError(MediaErrorClass.TRANSCRIPTION_RESPONSE_INVALID.value) from exc
            labels[speaker_label] = label
            segments.append(
                TranscriptSegment(
                    segment_id=f"provider-segment-{index + 1}",
                    speaker=Speaker.UNKNOWN_PARTICIPANT,
                    identity=SpeakerIdentity(
                        speaker=Speaker.UNKNOWN_PARTICIPANT,
                        asserted_label=None,
                        verification_state=ValueState.UNKNOWN,
                        raw_provider_speaker_label=speaker_label,
                    ),
                    start_seconds=start_value,
                    end_seconds=end_value,
                    text=segment_text,
                )
            )
        transcript = Transcript(
            transcript_id=self._transcript_id(call_id, inspection.hash_reference),
            call_id=call_id,
            language=cast(Any, language),
            diarization_status=DiarizationStatus.AVAILABLE,
            original_language_text=text,
            timestamp_availability=TimestampAvailability.AVAILABLE,
            provider_response_version=response_version,
            media_hash_reference=inspection.hash_reference,
            validation_state=TranscriptValidationState.ACCEPTED,
            segments=tuple(segments),
            provenance=provenance,
        )
        metadata = TranscriptionResponseMetadata(
            call_id=call_id,
            attempt_number=attempt_number,
            model_id=self.settings.transcription_model_id,
            provider_response_version=response_version,
            language=cast(Any, language),
            timestamp_availability=MediaTimestampAvailability.AVAILABLE,
            diarization_availability=DiarizationAvailability.AVAILABLE,
            speaker_labels=tuple(labels.values()),
            usage=usage,
        )
        return transcript, metadata

    @staticmethod
    def _response_payload(response: object) -> dict[str, Any]:
        if isinstance(response, BaseModel):
            return response.model_dump(mode="json", warnings="none")
        if isinstance(response, dict):
            return cast(dict[str, Any], response)
        if isinstance(response, str):
            parsed = json.loads(response)
            if isinstance(parsed, dict):
                return cast(dict[str, Any], parsed)
        raise ValueError(MediaErrorClass.TRANSCRIPTION_RESPONSE_INVALID.value)

    @staticmethod
    def _usage(raw: object) -> TranscriptionUsageMetadata | None:
        if not isinstance(raw, dict):
            return None
        input_tokens = raw.get("input_tokens")
        output_tokens = raw.get("output_tokens")
        duration = raw.get("seconds", raw.get("duration_seconds"))
        return TranscriptionUsageMetadata(
            input_tokens=input_tokens if isinstance(input_tokens, int) else None,
            output_tokens=output_tokens if isinstance(output_tokens, int) else None,
            duration_seconds=float(duration) if isinstance(duration, int | float) else None,
        )

    @staticmethod
    def _transcript_id(call_id: str, hash_reference: str) -> str:
        return hashlib.sha256(f"{call_id}:{hash_reference}".encode()).hexdigest()[:32]

    @staticmethod
    def _retry_after(exc: Exception) -> float | None:
        if not isinstance(exc, APIStatusError):
            return None
        raw = exc.response.headers.get("retry-after")
        if raw is None:
            return None
        try:
            value = float(raw)
        except ValueError:
            return None
        return value if 0 <= value <= 10 else None

    def _classify_exception(
        self, exc: Exception, attempt_number: int
    ) -> TranscriptionErrorClassification:
        retry_after = self._retry_after(exc)
        if isinstance(exc, AuthenticationError):
            error_class = MediaErrorClass.TRANSCRIPTION_AUTH_FAILED
            retryable = False
        elif isinstance(exc, APITimeoutError | APIConnectionError):
            error_class = MediaErrorClass.TRANSCRIPTION_TIMEOUT
            retryable = True
        elif isinstance(exc, RateLimitError):
            error_class = MediaErrorClass.TRANSCRIPTION_RATE_LIMITED
            retryable = True
        elif isinstance(exc, APIStatusError) and exc.status_code >= 500:
            error_class = MediaErrorClass.TRANSCRIPTION_PROVIDER_FAILED
            retryable = True
        elif isinstance(exc, ValueError | ValidationError | json.JSONDecodeError):
            error_class = MediaErrorClass.TRANSCRIPTION_RESPONSE_INVALID
            retryable = False
        else:
            error_class = MediaErrorClass.TRANSCRIPTION_PROVIDER_FAILED
            retryable = False
        return TranscriptionErrorClassification(
            error_class=error_class,
            retryable=retryable,
            attempt_number=attempt_number,
            retry_after_seconds=retry_after,
        )

    def _retry_delay(
        self, classification: TranscriptionErrorClassification, attempt_number: int
    ) -> float:
        if classification.retry_after_seconds is not None:
            return classification.retry_after_seconds
        jitter = self.jitter()
        if jitter < 0 or jitter > 1:
            raise ValueError("jitter source must return a value between zero and one")
        return float(min(10.0, float(2 ** (attempt_number - 1)) + jitter))

    @staticmethod
    def _invalid_configuration(call_id: str) -> TranscriptionAdapterError:
        del call_id
        classification = TranscriptionErrorClassification(
            error_class=MediaErrorClass.TRANSCRIPTION_PROVIDER_FAILED,
            retryable=False,
            attempt_number=1,
        )
        return TranscriptionAdapterError(classification, ())


def create_live_openai_transcriber(settings: Settings) -> OpenAITranscriber:
    """Reject live construction in Slice 3A regardless of ambient credentials."""

    del settings
    raise LiveTranscriptionBlockedError("slice3b_authorization_and_factory_not_implemented")
