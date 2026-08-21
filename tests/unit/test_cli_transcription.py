from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from packages.config import AppProfile, Settings
from packages.contracts.media import (
    MediaContentType,
    MediaErrorClass,
    MediaInspectionResult,
    SupportedMediaFormat,
    TemporaryObjectReference,
)
from packages.contracts.review import (
    CallSource,
    Direction,
    NormalizedCall,
    Provenance,
    TranscriptionTransportProvenance,
    TranscriptValidationState,
)
from packages.transcription import (
    CliCapabilityState,
    CliExecutionAuthorization,
    CommandRequest,
    CommandResult,
    CommandRunError,
    LiveTranscriptionBlockedError,
    OpenAICliLocalClient,
    TranscriptionAdapterError,
    create_local_cli_transcriber,
    evaluate_cli_capability,
)

FIXTURE_ROOT = Path("fixtures/transcription-responses")


class FakeRunner:
    executes_process = False

    def __init__(self, outcomes: list[CommandResult | CommandRunError]) -> None:
        self.outcomes = iter(outcomes)
        self.requests: list[CommandRequest] = []

    def run(self, request: CommandRequest) -> CommandResult:
        self.requests.append(request)
        outcome = next(self.outcomes)
        if isinstance(outcome, CommandRunError):
            raise outcome
        return outcome


class DeclaredProcessRunner(FakeRunner):
    """Gate-test double that declares process intent but never receives a run call."""

    executes_process = True


class Resolver:
    def __init__(
        self, reference: TemporaryObjectReference, inspection: MediaInspectionResult, path: Path
    ) -> None:
        self.item = (reference, inspection, path)

    def resolve_media(
        self, media_reference: str
    ) -> tuple[TemporaryObjectReference, MediaInspectionResult, object]:
        assert media_reference == "generated-media"
        return self.item


def _response(name: str) -> CommandResult:
    return CommandResult(
        return_code=0,
        stdout=(FIXTURE_ROOT / f"{name}.json").read_bytes(),
        stderr=b"",
    )


def _failure(stderr: bytes) -> CommandResult:
    return CommandResult(return_code=1, stdout=b"", stderr=stderr)


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        app_profile=AppProfile.LOCAL_DEV,
        call_source_adapter="generated_synthetic",
        transcriber_adapter="openai_cli_local",
        analyzer_adapter="disabled",
        media_temp_root="/tmp/colacci-law-slice3c/objects",
    )


def _inspection(*, seconds: float = 12.0) -> MediaInspectionResult:
    return MediaInspectionResult(
        artifact_id="generated-artifact",
        synthetic=True,
        media_format=SupportedMediaFormat.WAV,
        content_type=MediaContentType.AUDIO_WAV,
        byte_size=16,
        duration_seconds=seconds,
        sample_rate_hz=16000,
        channel_count=1,
        codec="pcm-s16le",
        content_sha256="a" * 64,
        inspected_at=datetime.now(UTC),
    )


def _call(*, seconds: float = 12.0, language: str = "en") -> NormalizedCall:
    return NormalizedCall(
        source=CallSource.FIXTURE,
        source_event_id="event-cli-local",
        source_call_id="call-cli-local",
        occurred_at=datetime.now(UTC),
        direction=Direction.UNKNOWN,
        duration_seconds=seconds,
        language_hint=cast(Any, language),
        media_reference="generated-media",
        synthetic=True,
    )


def _provenance(call: NormalizedCall) -> Provenance:
    return Provenance(
        schema_version="review-contracts-v1",
        call_source=call.source,
        source_event_id=call.source_event_id,
        source_call_id=call.source_call_id,
        transcript_adapter="openai_cli_local",
        transcript_model_version="gpt-4o-transcribe-diarize",
        analysis_adapter="disabled",
        analysis_model_version="deterministic-analysis-v1",
        prompt_version="facts-first-prompt-v1",
        playbook_version="synthetic-draft-v1",
        adapter_version="openai-cli-audio-transcriptions-v1",
        generated_at=datetime.now(UTC),
        processing_attempt_id="attempt-cli-local",
        environment="local_dev",
        transcription_transport=TranscriptionTransportProvenance(
            transport="openai_cli_local",
            declared_contract_version="openai-cli-audio-transcriptions-v1",
            observed_cli_version="1.6.0",
            model_id="gpt-4o-transcribe-diarize",
            requested_response_format="diarized_json",
            generated_asset_fingerprint="sha256:aaaaaaaaaaaa",
            attempt_number=1,
            result_kind="deterministic_fixture",
        ),
    )


def _adapter(
    tmp_path: Path,
    runner: FakeRunner,
    *,
    seconds: float = 12.0,
    sleeps: list[float] | None = None,
) -> tuple[Any, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    media_path = tmp_path / "invented.wav"
    media_path.write_bytes(b"RIFF-invented")
    inspection = _inspection(seconds=seconds)
    reference = TemporaryObjectReference(
        object_id="generated-object",
        artifact_id=inspection.artifact_id,
        store_name="local-synthetic-v1",
        synthetic=True,
        created_at=datetime.now(UTC),
    )
    input_root = tmp_path / "cli-inputs"
    adapter = create_local_cli_transcriber(
        _settings(),
        media_resolver=Resolver(reference, inspection, media_path),
        runner=runner,
        executable=Path("/fake/openai"),
        input_root=input_root,
        sleeper=(sleeps.append if sleeps is not None else lambda _: None),
    )
    return adapter, input_root


def _transcribe(adapter: Any, *, seconds: float = 12.0, language: str = "en") -> Any:
    call = _call(seconds=seconds, language=language)
    return adapter.transcribe(
        call,
        fixture_id="CLI-FX-001",
        call_id="internal-call-cli",
        attempt_number=1,
        provenance=_provenance(call),
    )


def test_cli_success_uses_argument_array_normalizes_and_cleans_up(tmp_path: Path) -> None:
    runner = FakeRunner([_response("english-diarized")])
    adapter, input_root = _adapter(tmp_path, runner)
    transcript = _transcribe(adapter)
    assert transcript.language == "en"
    assert transcript.validation_state is TranscriptValidationState.ACCEPTED
    assert {item.identity.raw_provider_speaker_label for item in transcript.segments} == {
        "speaker_0",
        "speaker_1",
    }
    request = runner.requests[0]
    assert request.arguments[:4] == (
        "audio:transcriptions",
        "create",
        "--model",
        "gpt-4o-transcribe-diarize",
    )
    assert "--response-format" in request.arguments
    assert "--format" in request.arguments
    assert "--api-key" not in request.arguments
    assert isinstance(request.arguments, tuple)
    assert not input_root.exists()
    client = cast(OpenAICliLocalClient, adapter.client)
    assert client.cleanup_confirmations == [True]


def test_long_audio_requests_automatic_chunking(tmp_path: Path) -> None:
    runner = FakeRunner([_response("english-diarized")])
    adapter, _ = _adapter(tmp_path, runner, seconds=38)
    _transcribe(adapter, seconds=38)
    arguments = runner.requests[0].arguments
    index = arguments.index("--chunking-strategy")
    assert arguments[index + 1] == "auto"


def test_spanish_and_opaque_multiple_speakers_are_preserved(tmp_path: Path) -> None:
    spanish_runner = FakeRunner([_response("spanish-diarized")])
    spanish, _ = _adapter(tmp_path / "spanish", spanish_runner)
    assert _transcribe(spanish, language="es").language == "es"

    speakers_runner = FakeRunner([_response("two-unknown-speakers")])
    speakers, _ = _adapter(tmp_path / "speakers", speakers_runner)
    transcript = _transcribe(speakers)
    assert len({item.identity.raw_provider_speaker_label for item in transcript.segments}) == 2
    assert all(item.speaker.value == "unknown_participant" for item in transcript.segments)


def test_text_only_fallback_remains_unaccepted_for_evidence(tmp_path: Path) -> None:
    runner = FakeRunner([_response("text-only-fallback")])
    adapter, _ = _adapter(tmp_path, runner)
    transcript = _transcribe(adapter)
    assert transcript.validation_state is TranscriptValidationState.REQUIRES_HUMAN_REVIEW
    assert transcript.segments == ()


@pytest.mark.parametrize(
    ("outcome", "expected", "attempts"),
    [
        (_failure(b"authentication failed"), MediaErrorClass.TRANSCRIPTION_AUTH_FAILED, 1),
        (_failure(b"terminal provider failure"), MediaErrorClass.TRANSCRIPTION_PROVIDER_FAILED, 1),
        (CommandRunError("cancelled"), MediaErrorClass.TRANSCRIPTION_CANCELLED, 1),
        (CommandRunError("output_oversized"), MediaErrorClass.TRANSCRIPTION_RESPONSE_INVALID, 1),
        (CommandRunError("executable_missing"), MediaErrorClass.TRANSCRIPTION_PROVIDER_FAILED, 1),
        (
            CommandResult(return_code=0, stdout=b"not-json", stderr=b""),
            MediaErrorClass.TRANSCRIPTION_RESPONSE_INVALID,
            1,
        ),
        (
            CommandResult(return_code=0, stdout=b"[]", stderr=b""),
            MediaErrorClass.TRANSCRIPTION_RESPONSE_INVALID,
            1,
        ),
    ],
)
def test_terminal_cli_outcomes_are_typed_and_always_cleaned(
    tmp_path: Path,
    outcome: CommandResult | CommandRunError,
    expected: MediaErrorClass,
    attempts: int,
) -> None:
    runner = FakeRunner([outcome])
    adapter, input_root = _adapter(tmp_path, runner)
    with pytest.raises(TranscriptionAdapterError) as raised:
        _transcribe(adapter)
    assert raised.value.classification.error_class is expected
    assert len(raised.value.attempts) == attempts
    assert not input_root.exists()


def test_timeout_is_capped_and_rate_limit_retries_once_then_succeeds(tmp_path: Path) -> None:
    sleeps: list[float] = []
    timeout_runner = FakeRunner(
        [CommandRunError("timeout"), CommandRunError("timeout"), CommandRunError("timeout")]
    )
    timeout_adapter, timeout_root = _adapter(tmp_path / "timeout", timeout_runner, sleeps=sleeps)
    with pytest.raises(TranscriptionAdapterError) as timeout:
        _transcribe(timeout_adapter)
    assert timeout.value.classification.error_class is MediaErrorClass.TRANSCRIPTION_TIMEOUT
    assert len(timeout.value.attempts) == 3
    assert sleeps == [1.0, 2.0]
    assert not timeout_root.exists()

    rate_sleeps: list[float] = []
    rate_runner = FakeRunner([_failure(b"rate limit 429"), _response("english-diarized")])
    rate_adapter, rate_root = _adapter(tmp_path / "rate", rate_runner, sleeps=rate_sleeps)
    assert _transcribe(rate_adapter).language == "en"
    assert len(rate_runner.requests) == 2
    assert rate_sleeps == [1.0]
    assert not rate_root.exists()


@pytest.mark.parametrize(
    ("version", "surface", "state"),
    [
        ("1.6.0", True, CliCapabilityState.SUPPORTED),
        ("1.3.7", False, CliCapabilityState.UNSUPPORTED),
        ("1.5.0", True, CliCapabilityState.UNSUPPORTED),
        ("1.6.0", False, CliCapabilityState.UNSUPPORTED),
    ],
)
def test_declared_cli_version_and_command_surface_are_both_required(
    version: str, surface: bool, state: CliCapabilityState
) -> None:
    capability = evaluate_cli_capability(
        observed_version=version,
        command_surface_supported=surface,
        path_classification="homebrew_standard",
    )
    assert capability.state is state


def test_preflight_report_contains_only_sanitized_presence_and_zero_usage() -> None:
    capability = evaluate_cli_capability(
        observed_version="1.3.7",
        command_surface_supported=False,
        path_classification="homebrew_standard",
    )
    report = capability.safe_report({"OPENAI_API_KEY": "ignored", "OPENAI_PROJECT_ID": "ignored"})
    assert report["credential_present"] is True
    assert report["project_configuration_present"] is True
    assert report["request_count"] == 0
    assert report["uploaded_bytes"] == 0
    rendered = json.dumps(report)
    assert "ignored" not in rendered
    assert "/opt/" not in rendered


@pytest.mark.parametrize(
    "command_request",
    [
        CommandRequest(executable=Path("openai"), arguments=("--help",)),
        CommandRequest(executable=Path("/fake/openai"), arguments=()),
        CommandRequest(executable=Path("/fake/openai"), arguments=("bad\x00arg",)),
        CommandRequest(executable=Path("/fake/openai"), arguments=("--api-key", "hidden")),
        CommandRequest(executable=Path("/fake/openai"), arguments=("--help",), timeout_seconds=0),
        CommandRequest(executable=Path("/fake/openai"), arguments=("--help",), timeout_seconds=121),
        CommandRequest(
            executable=Path("/fake/openai"), arguments=("--help",), output_limit_bytes=0
        ),
        CommandRequest(
            executable=Path("/fake/openai"),
            arguments=("--help",),
            output_limit_bytes=1024 * 1024 + 1,
        ),
    ],
)
def test_command_request_rejects_unsafe_process_shapes(command_request: CommandRequest) -> None:
    with pytest.raises(ValueError):
        command_request.validate()


def _authorization(
    *, approval_reference: str = "OWNER-CHAT-2026-08-17-SLICE-3B"
) -> CliExecutionAuthorization:
    return CliExecutionAuthorization(
        approval_reference=approval_reference,
        generated_only=True,
        account_data_controls_approved=True,
        max_requests=4,
        max_retries=1,
        max_total_audio_seconds=120,
        max_total_bytes=20 * 1024 * 1024,
        max_budget_usd="1.00",
    )


def test_local_cli_factory_rejects_every_missing_process_authority(tmp_path: Path) -> None:
    runner = DeclaredProcessRunner([])
    resolver = cast(Any, object())
    executable = Path("/fake/openai")
    supported = evaluate_cli_capability(
        observed_version="1.6.0",
        command_surface_supported=True,
        path_classification="test_allowlisted",
        executable=executable,
    )

    with pytest.raises(LiveTranscriptionBlockedError, match="local_dev_profile_required"):
        create_local_cli_transcriber(
            Settings(_env_file=None),
            media_resolver=resolver,
            runner=runner,
            executable=executable,
        )

    transcript_settings = Settings(
        _env_file=None,
        app_profile=AppProfile.LOCAL_DEV,
        call_source_adapter="transcript_only",
        transcriber_adapter="transcript_only_import",
        analyzer_adapter="fixture",
        media_temp_root="/tmp/colacci-law-slice3c/objects",
    )
    with pytest.raises(LiveTranscriptionBlockedError, match="local_cli_adapter_shape_required"):
        create_local_cli_transcriber(
            transcript_settings,
            media_resolver=resolver,
            runner=runner,
            executable=executable,
        )

    with pytest.raises(LiveTranscriptionBlockedError, match="supported_openai_cli_required"):
        create_local_cli_transcriber(
            _settings(),
            media_resolver=resolver,
            runner=runner,
            executable=executable,
        )
    with pytest.raises(LiveTranscriptionBlockedError, match="slice3b_cli_authorization_required"):
        create_local_cli_transcriber(
            _settings(),
            media_resolver=resolver,
            runner=runner,
            executable=executable,
            capability=supported,
        )
    with pytest.raises(LiveTranscriptionBlockedError, match="slice3b_cli_authorization_required"):
        create_local_cli_transcriber(
            _settings(),
            media_resolver=resolver,
            runner=runner,
            executable=executable,
            capability=supported,
            authorization=_authorization(approval_reference="not-authorized"),
        )
    with pytest.raises(LiveTranscriptionBlockedError, match="live_project_credentials_required"):
        create_local_cli_transcriber(
            _settings(),
            media_resolver=resolver,
            runner=runner,
            executable=executable,
            capability=supported,
            authorization=_authorization(),
        )

    adapter = create_local_cli_transcriber(
        _settings(),
        media_resolver=resolver,
        runner=runner,
        executable=executable,
        capability=supported,
        authorization=_authorization(),
        child_environment={"OPENAI_API_KEY": "unused", "OPENAI_PROJECT_ID": "unused"},
        input_root=tmp_path,
    )
    assert adapter.adapter_name == "openai_cli_local"
    assert runner.requests == []
