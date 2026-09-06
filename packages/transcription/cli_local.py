"""Local-only CLI capability and transcription contract adapter."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

from packages.config import AppProfile, Settings
from packages.contracts.media import MediaErrorClass
from packages.transcription.cli_process import (
    DEFAULT_OUTPUT_LIMIT_BYTES,
    DEFAULT_TIMEOUT_SECONDS,
    CommandRequest,
    CommandResult,
    CommandRunError,
    CommandRunner,
    ProcessCommandRunner,
)
from packages.transcription.live import (
    APPROVED_MODEL,
    AUTHORIZATION_REFERENCE,
    MAX_BUDGET_USD,
    MAX_REQUESTS,
    MAX_TOTAL_AUDIO_SECONDS,
    MAX_TOTAL_BYTES,
)
from packages.transcription.openai_adapter import (
    LiveTranscriptionBlockedError,
    MediaResolver,
    OpenAITranscriber,
    SafeTranscriptionTransportError,
)

DECLARED_OPENAI_CLI_VERSION = "1.6.0"
DECLARED_CLI_CONTRACT_VERSION = "openai-cli-audio-transcriptions-v1"
SUPPORTED_OPENAI_CLI_VERSIONS = frozenset({DECLARED_OPENAI_CLI_VERSION})
CLI_MODEL = APPROVED_MODEL
CLI_RESPONSE_FORMAT = "diarized_json"
CLI_TEMP_ROOT = Path("/tmp/colacci-law-slice3c/cli-inputs")  # noqa: S108  # nosec B108
SAFE_DISCOVERY_PATHS = (
    (Path("/opt/homebrew/bin/openai"), "homebrew_standard"),
    (Path("/usr/local/bin/openai"), "usr_local_standard"),
    (Path("/usr/bin/openai"), "system_standard"),
)
REQUIRED_ROOT_HELP_MARKERS = (
    "audio:transcriptions",
    "--format",
)
REQUIRED_TRANSCRIPTION_HELP_MARKERS = (
    "audio:transcriptions create",
    "--model",
    "--file",
    "--response-format",
    "--chunking-strategy",
)


class CliCapabilityState(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class CliCapability:
    state: CliCapabilityState
    path_classification: str
    declared_version: str
    observed_version: str
    command_surface_supported: bool
    executable: Path | None = field(default=None, repr=False)

    def safe_report(self, environment: Mapping[str, str]) -> dict[str, object]:
        return {
            "schema_version": "slice3c-cli-preflight-v1",
            "execution_profile": AppProfile.LOCAL_DEV.value,
            "cli_path_classification": self.path_classification,
            "declared_cli_version": self.declared_version,
            "declared_cli_contract_version": DECLARED_CLI_CONTRACT_VERSION,
            "observed_cli_version": self.observed_version,
            "cli_state": self.state.value,
            "supported_command_surface": self.command_surface_supported,
            "command_surface_contract": (
                "audio-transcriptions-create-diarized-json-chunking-auto-v1"
            ),
            "generated_only_boundary": True,
            "credential_present": "OPENAI_API_KEY" in environment,
            "project_configuration_present": "OPENAI_PROJECT_ID" in environment,
            "selected_deterministic_fallback": "fixture-and-transcript-only",
            "live_execution_disabled": True,
            "network_operation_allowed": False,
            "provider_client_constructed": False,
            "request_count": 0,
            "retry_count": 0,
            "uploaded_bytes": 0,
            "uploaded_seconds": 0,
            "cost_usd": "0.00",
        }


def inspect_cli_capability() -> CliCapability:
    candidate: Path | None = None
    classification = "unavailable"
    for path, path_classification in SAFE_DISCOVERY_PATHS:
        if path.is_file() and os.access(path, os.X_OK):
            candidate = path
            classification = path_classification
            break
    if candidate is None:
        return CliCapability(
            state=CliCapabilityState.UNAVAILABLE,
            path_classification=classification,
            declared_version=DECLARED_OPENAI_CLI_VERSION,
            observed_version="unavailable",
            command_surface_supported=False,
        )
    runner = ProcessCommandRunner(allowed_executables=frozenset({candidate}))
    observed = "unavailable"
    try:
        version_result = runner.run(
            CommandRequest(executable=candidate, arguments=("--version",), timeout_seconds=3)
        )
        combined_version = (version_result.stdout + version_result.stderr).decode(
            "utf-8", errors="ignore"
        )
        match = re.search(r"(?<![0-9])([0-9]+\.[0-9]+\.[0-9]+)(?![0-9])", combined_version)
        if match:
            observed = match.group(1)
        root_help_result = runner.run(
            CommandRequest(
                executable=candidate,
                arguments=("--help",),
                timeout_seconds=3,
                output_limit_bytes=128 * 1024,
            )
        )
        transcription_help_result = runner.run(
            CommandRequest(
                executable=candidate,
                arguments=("audio:transcriptions", "create", "--help"),
                timeout_seconds=3,
                output_limit_bytes=128 * 1024,
            )
        )
        root_help = (root_help_result.stdout + root_help_result.stderr).decode(
            "utf-8", errors="ignore"
        )
        transcription_help = (
            transcription_help_result.stdout + transcription_help_result.stderr
        ).decode("utf-8", errors="ignore")
        surface_supported = (
            root_help_result.return_code == 0
            and transcription_help_result.return_code == 0
            and all(marker in root_help for marker in REQUIRED_ROOT_HELP_MARKERS)
            and all(marker in transcription_help for marker in REQUIRED_TRANSCRIPTION_HELP_MARKERS)
        )
    except CommandRunError:
        surface_supported = False
    return evaluate_cli_capability(
        observed_version=observed,
        command_surface_supported=surface_supported,
        path_classification=classification,
        executable=candidate,
    )


def evaluate_cli_capability(
    *,
    observed_version: str,
    command_surface_supported: bool,
    path_classification: str,
    executable: Path | None = None,
) -> CliCapability:
    supported = observed_version in SUPPORTED_OPENAI_CLI_VERSIONS and command_surface_supported
    return CliCapability(
        state=CliCapabilityState.SUPPORTED if supported else CliCapabilityState.UNSUPPORTED,
        path_classification=path_classification,
        declared_version=DECLARED_OPENAI_CLI_VERSION,
        observed_version=observed_version,
        command_surface_supported=command_surface_supported,
        executable=executable,
    )


@dataclass(frozen=True)
class CliExecutionAuthorization:
    approval_reference: str
    generated_only: bool
    account_data_controls_approved: bool
    max_requests: int
    max_retries: int
    max_total_audio_seconds: float
    max_total_bytes: int
    max_budget_usd: str

    def validate(self) -> None:
        if (
            self.approval_reference != AUTHORIZATION_REFERENCE
            or not self.generated_only
            or not self.account_data_controls_approved
            or self.max_requests != MAX_REQUESTS
            or self.max_retries != 1
            or self.max_total_audio_seconds != MAX_TOTAL_AUDIO_SECONDS
            or self.max_total_bytes != MAX_TOTAL_BYTES
            or self.max_budget_usd != str(MAX_BUDGET_USD)
        ):
            raise LiveTranscriptionBlockedError("slice3b_cli_authorization_required")


class OpenAICliLocalClient:
    """SDK-shaped shim that delegates only to the validated local CLI argument array."""

    def __init__(
        self,
        *,
        runner: CommandRunner,
        executable: Path,
        child_environment: Mapping[str, str],
        input_root: Path = CLI_TEMP_ROOT,
        cancelled: Callable[[], bool] = lambda: False,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        output_limit_bytes: int = DEFAULT_OUTPUT_LIMIT_BYTES,
    ) -> None:
        self.audio = self
        self.transcriptions = self
        self.runner = runner
        self.executable = executable
        self.child_environment = dict(child_environment)
        self.input_root = input_root
        self.cancelled = cancelled
        self.timeout_seconds = timeout_seconds
        self.output_limit_bytes = output_limit_bytes
        self.cleanup_confirmations: list[bool] = []

    def create(self, **kwargs: Any) -> object:
        self._validate_request(kwargs)
        self.input_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.input_root, 0o700)
        temporary_directory = Path(tempfile.mkdtemp(prefix="cli-", dir=self.input_root))
        os.chmod(temporary_directory, 0o700)
        input_path = temporary_directory / "generated-input.wav"
        try:
            file_value = cast(tuple[str, object, str], kwargs["file"])
            source = file_value[1]
            with input_path.open("xb") as destination:
                os.chmod(input_path, 0o600)
                total = 0
                while True:
                    chunk = cast(Any, source).read(64 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_TOTAL_BYTES:
                        raise SafeTranscriptionTransportError(
                            error_class=MediaErrorClass.OVERSIZED_MEDIA,
                            retryable=False,
                        )
                    destination.write(chunk)
            arguments = [
                "audio:transcriptions",
                "create",
                "--model",
                str(kwargs["model"]),
                "--file",
                str(input_path),
                "--response-format",
                str(kwargs["response_format"]),
                "--format",
                "json",
            ]
            language = kwargs.get("language")
            if language is not None:
                arguments.extend(("--language", str(language)))
            if kwargs.get("chunking_strategy") == "auto":
                arguments.extend(("--chunking-strategy", "auto"))
            try:
                result = self.runner.run(
                    CommandRequest(
                        executable=self.executable,
                        arguments=tuple(arguments),
                        environment=self.child_environment,
                        timeout_seconds=self.timeout_seconds,
                        output_limit_bytes=self.output_limit_bytes,
                        cancelled=self.cancelled,
                    )
                )
            except CommandRunError as exc:
                raise self._map_runner_failure(exc) from exc
            if result.return_code != 0:
                raise self._map_nonzero(result)
            try:
                payload = json.loads(result.stdout)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise SafeTranscriptionTransportError(
                    error_class=MediaErrorClass.TRANSCRIPTION_RESPONSE_INVALID,
                    retryable=False,
                ) from exc
            if not isinstance(payload, dict):
                raise SafeTranscriptionTransportError(
                    error_class=MediaErrorClass.TRANSCRIPTION_RESPONSE_INVALID,
                    retryable=False,
                )
            if "language" not in payload and language in {"en", "es"}:
                payload["language"] = language
            return payload
        finally:
            shutil.rmtree(temporary_directory, ignore_errors=True)
            cleaned = not temporary_directory.exists()
            self.cleanup_confirmations.append(cleaned)
            if not cleaned:
                raise SafeTranscriptionTransportError(
                    error_class=MediaErrorClass.MEDIA_DELETION_FAILED,
                    retryable=False,
                )
            try:
                if self.input_root.exists() and not any(self.input_root.iterdir()):
                    self.input_root.rmdir()
            except OSError:
                # Only the empty shared parent is optional; request media was verified gone.
                pass

    @staticmethod
    def _validate_request(kwargs: Mapping[str, Any]) -> None:
        if kwargs.get("model") != CLI_MODEL or kwargs.get("response_format") != CLI_RESPONSE_FORMAT:
            raise SafeTranscriptionTransportError(
                error_class=MediaErrorClass.TRANSCRIPTION_PROVIDER_FAILED,
                retryable=False,
            )
        file_value = kwargs.get("file")
        if (
            not isinstance(file_value, tuple)
            or len(file_value) != 3
            or not hasattr(file_value[1], "read")
        ):
            raise SafeTranscriptionTransportError(
                error_class=MediaErrorClass.TRANSCRIPTION_PROVIDER_FAILED,
                retryable=False,
            )
        if kwargs.get("chunking_strategy") not in {None, "auto"}:
            raise SafeTranscriptionTransportError(
                error_class=MediaErrorClass.TRANSCRIPTION_PROVIDER_FAILED,
                retryable=False,
            )

    @staticmethod
    def _map_runner_failure(exc: CommandRunError) -> SafeTranscriptionTransportError:
        if exc.code == "timeout":
            return SafeTranscriptionTransportError(
                error_class=MediaErrorClass.TRANSCRIPTION_TIMEOUT,
                retryable=True,
            )
        if exc.code == "cancelled":
            return SafeTranscriptionTransportError(
                error_class=MediaErrorClass.TRANSCRIPTION_CANCELLED,
                retryable=False,
            )
        if exc.code == "output_oversized":
            return SafeTranscriptionTransportError(
                error_class=MediaErrorClass.TRANSCRIPTION_RESPONSE_INVALID,
                retryable=False,
            )
        return SafeTranscriptionTransportError(
            error_class=MediaErrorClass.TRANSCRIPTION_PROVIDER_FAILED,
            retryable=False,
        )

    @staticmethod
    def _map_nonzero(result: CommandResult) -> SafeTranscriptionTransportError:
        diagnostic = result.stderr[:8192].lower()
        if any(marker in diagnostic for marker in (b"authentication", b"api key", b"401")):
            error_class = MediaErrorClass.TRANSCRIPTION_AUTH_FAILED
            retryable = False
        elif any(marker in diagnostic for marker in (b"rate limit", b"429")):
            error_class = MediaErrorClass.TRANSCRIPTION_RATE_LIMITED
            retryable = True
        elif any(marker in diagnostic for marker in (b"temporarily unavailable", b"500", b"503")):
            error_class = MediaErrorClass.TRANSCRIPTION_PROVIDER_FAILED
            retryable = True
        else:
            error_class = MediaErrorClass.TRANSCRIPTION_PROVIDER_FAILED
            retryable = False
        return SafeTranscriptionTransportError(error_class=error_class, retryable=retryable)


def create_local_cli_transcriber(
    settings: Settings,
    *,
    media_resolver: MediaResolver,
    runner: CommandRunner,
    executable: Path,
    child_environment: Mapping[str, str] | None = None,
    capability: CliCapability | None = None,
    authorization: CliExecutionAuthorization | None = None,
    cancelled: Callable[[], bool] = lambda: False,
    input_root: Path = CLI_TEMP_ROOT,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
    jitter: Callable[[], float] = lambda: 0.0,
) -> OpenAITranscriber:
    """Create the dev-only adapter; process execution needs the unchanged Slice 3B gate."""

    validated = Settings(_env_file=None, **settings.model_dump())  # type: ignore[call-arg]
    if validated.app_profile is not AppProfile.LOCAL_DEV:
        raise LiveTranscriptionBlockedError("local_dev_profile_required")
    if (
        validated.call_source_adapter != "generated_synthetic"
        or validated.transcriber_adapter != "openai_cli_local"
        or validated.analyzer_adapter != "disabled"
    ):
        raise LiveTranscriptionBlockedError("local_cli_adapter_shape_required")
    environment = dict(child_environment or {})
    if runner.executes_process:
        if capability is None or capability.state is not CliCapabilityState.SUPPORTED:
            raise LiveTranscriptionBlockedError("supported_openai_cli_required")
        if authorization is None:
            raise LiveTranscriptionBlockedError("slice3b_cli_authorization_required")
        authorization.validate()
        if "OPENAI_API_KEY" not in environment or "OPENAI_PROJECT_ID" not in environment:
            raise LiveTranscriptionBlockedError("live_project_credentials_required")
    client = OpenAICliLocalClient(
        runner=runner,
        executable=executable,
        child_environment=environment,
        input_root=input_root,
        cancelled=cancelled,
        timeout_seconds=validated.transcription_timeout_seconds,
    )
    return OpenAITranscriber(
        client=cast(Any, client),
        media_resolver=media_resolver,
        settings=validated,
        clock=clock,
        sleeper=sleeper,
        jitter=jitter,
        adapter_name="openai_cli_local",
        adapter_version=DECLARED_CLI_CONTRACT_VERSION,
    )
