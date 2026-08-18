from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx2
import pytest
from openai import BadRequestError, PermissionDeniedError
from pydantic import ValidationError

from packages.config import AppProfile, Settings
from packages.contracts.media import (
    MediaContentType,
    MediaErrorClass,
    MediaInspectionResult,
    SupportedMediaFormat,
    TranscriptionUsageMetadata,
)
from packages.transcription import (
    LiveTranscriptionBlockedError,
    OpenAITranscriber,
    create_live_openai_transcriber,
)
from packages.transcription.live import LiveRunBudget, LiveRunLimitError, live_gate_failures


def live_values(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "_env_file": None,
        "app_profile": AppProfile.LIVE_TEST,
        "allow_real_call_data": False,
        "real_call_processing_authorized": False,
        "live_transcription_enabled": True,
        "live_transcription_authorized": True,
        "transcription_approval_reference": "OWNER-CHAT-2026-08-17-SLICE-3B",
        "transcription_model_id": "gpt-4o-transcribe-diarize",
        "transcription_max_requests": 4,
        "transcription_max_total_audio_seconds": 120,
        "transcription_max_total_bytes": 20 * 1024 * 1024,
        "transcription_test_budget_usd": Decimal("1.00"),
        "transcription_live_execution_confirmed": True,
        "openai_api_key": "ephemeral-unit-value",
        "openai_project_id": "project-unit-value",
        "openai_project_data_controls_approved": True,
        "openai_base_url": "https://api.openai.com/v1",
        "call_source_adapter": "generated_synthetic",
        "transcriber_adapter": "openai_live",
        "analyzer_adapter": "disabled",
        "notification_adapter": "noop",
        "object_storage_backend": "local_synthetic",
        "media_temp_root": "/tmp/colacci-law-slice3b/objects",
    }
    values.update(overrides)
    return values


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("app_profile", AppProfile.TEST),
        ("live_transcription_enabled", False),
        ("live_transcription_authorized", False),
        ("transcription_approval_reference", "wrong-authorization"),
        ("transcription_model_id", "wrong-model"),
        ("transcription_max_requests", 5),
        ("transcription_max_total_audio_seconds", 121),
        ("transcription_max_total_bytes", 20 * 1024 * 1024 + 1),
        ("transcription_test_budget_usd", Decimal("1.01")),
        ("openai_api_key", None),
        ("openai_project_id", None),
        ("openai_project_data_controls_approved", False),
        ("openai_base_url", "https://example.invalid/v1"),
        ("call_source_adapter", "fixture"),
        ("transcriber_adapter", "fixture"),
        ("analyzer_adapter", "fixture"),
        ("notification_adapter", "external"),
        ("object_storage_backend", "private_cloud"),
        ("allow_real_call_data", True),
        ("real_call_processing_authorized", True),
        ("media_temp_root", "/var/tmp/outside-boundary"),
        ("media_temp_root", "/tmp/colacci-law-other/objects"),
    ],
)
def test_live_settings_reject_each_gate(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        Settings(**live_values(**{field: value}))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("app_profile", AppProfile.TEST),
        ("live_transcription_enabled", False),
        ("live_transcription_authorized", False),
        ("transcription_approval_reference", "wrong-authorization"),
        ("transcription_model_id", "wrong-model"),
        ("transcription_max_requests", 3),
        ("transcription_max_total_audio_seconds", 119),
        ("transcription_max_total_bytes", 19),
        ("transcription_test_budget_usd", Decimal("0.99")),
        ("openai_api_key", None),
        ("openai_project_id", None),
        ("openai_project_data_controls_approved", False),
        ("openai_base_url", "https://example.invalid/v1"),
        ("call_source_adapter", "fixture"),
        ("transcriber_adapter", "fixture"),
        ("analyzer_adapter", "fixture"),
        ("notification_adapter", "external"),
        ("object_storage_backend", "private_cloud"),
        ("allow_real_call_data", True),
        ("real_call_processing_authorized", True),
        ("media_temp_root", "/var/tmp/outside-boundary"),
        ("media_temp_root", "/tmp/colacci-law-other/objects"),
    ],
)
def test_live_factory_revalidates_every_gate_before_client_construction(
    field: str, value: object
) -> None:
    valid = Settings(**live_values())
    unsafe = Settings.model_construct(**{**valid.model_dump(), field: value})
    constructions = 0

    def builder(_: Settings) -> Any:
        nonlocal constructions
        constructions += 1
        return object()

    with pytest.raises(LiveTranscriptionBlockedError):
        create_live_openai_transcriber(
            unsafe,
            media_resolver=object(),  # type: ignore[arg-type]
            request_guard=lambda _: None,
            client_builder=builder,
        )
    assert constructions == 0


def test_live_factory_requires_final_confirmation_then_constructs_once() -> None:
    unconfirmed = Settings(**live_values(transcription_live_execution_confirmed=False))
    constructions = 0

    def builder(_: Settings) -> Any:
        nonlocal constructions
        constructions += 1
        return object()

    with pytest.raises(LiveTranscriptionBlockedError, match="confirmation"):
        create_live_openai_transcriber(
            unconfirmed,
            media_resolver=object(),  # type: ignore[arg-type]
            request_guard=lambda _: None,
            client_builder=builder,
        )
    assert constructions == 0

    confirmed = Settings(**live_values())
    create_live_openai_transcriber(
        confirmed,
        media_resolver=object(),  # type: ignore[arg-type]
        request_guard=lambda _: None,
        client_builder=builder,
    )
    assert constructions == 1


def inspection(
    artifact_id: str, *, seconds: float = 10, byte_size: int = 100
) -> MediaInspectionResult:
    return MediaInspectionResult(
        artifact_id=artifact_id,
        synthetic=True,
        media_format=SupportedMediaFormat.WAV,
        content_type=MediaContentType.AUDIO_WAV,
        byte_size=byte_size,
        duration_seconds=seconds,
        sample_rate_hz=16000,
        channel_count=1,
        codec="pcm_s16le",
        content_sha256="a" * 64,
        inspected_at=datetime.now(UTC),
    )


def test_shared_budget_allows_three_primaries_and_only_one_retry() -> None:
    budget = LiveRunBudget()
    first = inspection("artifact-first")
    budget(first)
    budget(first)
    budget(inspection("artifact-second"))
    budget(inspection("artifact-third"))
    assert budget.request_count == 4
    assert budget.retry_count == 1
    with pytest.raises(LiveRunLimitError, match="request_cap"):
        budget(first)


def test_shared_budget_stops_duration_bytes_and_observed_cost_before_more_work() -> None:
    with pytest.raises(LiveRunLimitError, match="audio_duration_cap"):
        LiveRunBudget()(inspection("duration-cap", seconds=120.1))
    with pytest.raises(LiveRunLimitError, match="upload_byte_cap"):
        LiveRunBudget()(inspection("byte-cap", byte_size=20 * 1024 * 1024 + 1))
    budget = LiveRunBudget()
    with pytest.raises(LiveRunLimitError, match="observed_cost_cap"):
        budget.record_usage(TranscriptionUsageMetadata(input_tokens=1_000_000))


@pytest.mark.parametrize("error_type", [PermissionDeniedError, BadRequestError])
def test_permission_and_invalid_request_are_never_retryable(error_type: type[Exception]) -> None:
    request = httpx2.Request("POST", "https://api.openai.com/v1/audio/transcriptions")
    response = httpx2.Response(403 if error_type is PermissionDeniedError else 400, request=request)
    error = error_type("blocked", response=response, body=None)  # type: ignore[call-arg]
    adapter = OpenAITranscriber(
        client=object(),  # type: ignore[arg-type]
        media_resolver=object(),  # type: ignore[arg-type]
        settings=Settings(_env_file=None, app_profile=AppProfile.TEST),
    )
    classification = adapter._classify_exception(error, 1)
    assert classification.retryable is False
    assert classification.error_class in {
        MediaErrorClass.TRANSCRIPTION_AUTH_FAILED,
        MediaErrorClass.TRANSCRIPTION_PROVIDER_FAILED,
    }


def test_raw_preflight_gate_never_accepts_credentials_alone() -> None:
    failures = live_gate_failures({"OPENAI_API_KEY": "present", "OPENAI_PROJECT_ID": "present"})
    assert "app_profile" in failures
    assert "live_transcription_authorized" in failures
