"""Replaceable call source, transcriber, and analyzer interfaces."""

from __future__ import annotations

from typing import Protocol

from packages.contracts.review import (
    ExtractedFacts,
    IngestionEvent,
    NormalizedCall,
    Provenance,
    StructuredAnalysis,
    Transcript,
)


class CallSourceAdapter(Protocol):
    adapter_name: str
    adapter_version: str

    def events(self, fixture_id: str | None = None) -> tuple[IngestionEvent, ...]: ...


class TranscriberAdapter(Protocol):
    adapter_name: str
    adapter_version: str
    model_version: str

    def transcribe(
        self,
        call: NormalizedCall,
        *,
        fixture_id: str,
        call_id: str,
        attempt_number: int,
        provenance: Provenance,
    ) -> Transcript: ...


class AnalyzerAdapter(Protocol):
    adapter_name: str
    adapter_version: str
    model_version: str
    prompt_version: str

    def extract_facts(self, fixture_id: str, transcript: Transcript) -> ExtractedFacts: ...

    def apply_playbook(
        self,
        fixture_id: str,
        *,
        call_id: str,
        facts: ExtractedFacts,
        transcript: Transcript,
        provenance: Provenance,
    ) -> StructuredAnalysis: ...
