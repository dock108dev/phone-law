"""Explicit call-processing state transitions."""

from __future__ import annotations

from packages.contracts.review import ProcessingState

TERMINAL_STATES = frozenset(
    {
        ProcessingState.ANALYZED,
        ProcessingState.AUDIO_INVALID,
        ProcessingState.TRANSCRIPTION_FAILED,
        ProcessingState.OUTPUT_VALIDATION_FAILED,
        ProcessingState.ANALYSIS_FAILED,
    }
)

ALLOWED_TRANSITIONS: dict[ProcessingState, frozenset[ProcessingState]] = {
    ProcessingState.RECEIVED: frozenset({ProcessingState.VALIDATED}),
    ProcessingState.VALIDATED: frozenset({ProcessingState.QUEUED}),
    ProcessingState.QUEUED: frozenset({ProcessingState.MEDIA_READY, ProcessingState.AUDIO_INVALID}),
    ProcessingState.MEDIA_READY: frozenset(
        {ProcessingState.TRANSCRIBING, ProcessingState.AUDIO_INVALID}
    ),
    ProcessingState.TRANSCRIBING: frozenset(
        {
            ProcessingState.TRANSCRIBED,
            ProcessingState.TRANSCRIPTION_FAILED,
            ProcessingState.AUDIO_INVALID,
        }
    ),
    ProcessingState.TRANSCRIBED: frozenset({ProcessingState.EXTRACTING_FACTS}),
    ProcessingState.EXTRACTING_FACTS: frozenset(
        {ProcessingState.APPLYING_PLAYBOOK, ProcessingState.OUTPUT_VALIDATION_FAILED}
    ),
    ProcessingState.APPLYING_PLAYBOOK: frozenset(
        {
            ProcessingState.ANALYZED,
            ProcessingState.OUTPUT_VALIDATION_FAILED,
            ProcessingState.ANALYSIS_FAILED,
        }
    ),
}


class InvalidStateTransitionError(ValueError):
    """Raised when a normal transition attempts to bypass the state contract."""


def transition(current: ProcessingState, target: ProcessingState) -> ProcessingState:
    if target not in ALLOWED_TRANSITIONS.get(current, frozenset()):
        raise InvalidStateTransitionError(
            f"transition not allowed: {current.value} -> {target.value}"
        )
    return target


def start_explicit_retry(current: ProcessingState) -> ProcessingState:
    """Start a distinct attempt; this is the only terminal-state resume operation."""

    if current not in {
        ProcessingState.TRANSCRIPTION_FAILED,
        ProcessingState.ANALYSIS_FAILED,
    }:
        raise InvalidStateTransitionError(f"state is not retryable: {current.value}")
    return ProcessingState.RECEIVED
