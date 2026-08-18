"""Disabled-by-default candidate transcription adapter for Slice 3A."""

from packages.transcription.openai_adapter import (
    LiveTranscriptionBlockedError,
    OpenAITranscriber,
    TranscriptionAdapterError,
    create_live_openai_transcriber,
)

__all__ = [
    "LiveTranscriptionBlockedError",
    "OpenAITranscriber",
    "TranscriptionAdapterError",
    "create_live_openai_transcriber",
]
