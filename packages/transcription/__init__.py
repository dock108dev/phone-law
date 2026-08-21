"""Disabled-by-default candidate transcription adapter for Slice 3A."""

from packages.transcription.cli_local import (
    DECLARED_CLI_CONTRACT_VERSION,
    DECLARED_OPENAI_CLI_VERSION,
    CliCapability,
    CliCapabilityState,
    CliExecutionAuthorization,
    CommandRequest,
    CommandResult,
    CommandRunError,
    OpenAICliLocalClient,
    ProcessCommandRunner,
    create_local_cli_transcriber,
    evaluate_cli_capability,
    inspect_cli_capability,
)
from packages.transcription.openai_adapter import (
    LiveTranscriptionBlockedError,
    OpenAITranscriber,
    SafeTranscriptionTransportError,
    TranscriptionAdapterError,
    create_live_openai_transcriber,
)

__all__ = [
    "DECLARED_CLI_CONTRACT_VERSION",
    "DECLARED_OPENAI_CLI_VERSION",
    "CliCapability",
    "CliCapabilityState",
    "CliExecutionAuthorization",
    "CommandRequest",
    "CommandResult",
    "CommandRunError",
    "LiveTranscriptionBlockedError",
    "OpenAICliLocalClient",
    "OpenAITranscriber",
    "ProcessCommandRunner",
    "SafeTranscriptionTransportError",
    "TranscriptionAdapterError",
    "create_live_openai_transcriber",
    "create_local_cli_transcriber",
    "evaluate_cli_capability",
    "inspect_cli_capability",
]
