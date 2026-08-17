"""Deterministic fixture adapters backed by explicit expected responses."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

from packages.contracts.review import (
    AdvisoryStatus,
    AnalysisAcceptanceState,
    AppointmentFact,
    Confidence,
    DateFact,
    EvidenceReference,
    ExtractedFacts,
    IdentityClaim,
    IngestionEvent,
    MonetaryFigure,
    NormalizedCall,
    Provenance,
    ResponsibleRole,
    StaffCommitment,
    StructuredAnalysis,
    TextFact,
    Transcript,
    UnresolvedQuestion,
    ValueState,
)

MANIFEST_PATH = Path(__file__).parents[2] / "fixtures" / "manifest.json"


class FixtureAdapterError(RuntimeError):
    def __init__(
        self,
        *,
        failure_class: str,
        terminal_state: str,
        diagnostic_code: str,
        retryable: bool,
    ) -> None:
        super().__init__(diagnostic_code)
        self.failure_class = failure_class
        self.terminal_state = terminal_state
        self.diagnostic_code = diagnostic_code
        self.retryable = retryable


def _deterministic_id(kind: str, fixture_id: str) -> str:
    return hashlib.sha256(f"{kind}:{fixture_id}".encode()).hexdigest()[:32]


class FixtureManifest:
    def __init__(self, path: Path = MANIFEST_PATH) -> None:
        raw = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
        fixtures = cast(list[dict[str, Any]], raw["fixtures"])
        self.version = cast(str, raw["manifest_version"])
        self.expected_provenance = cast(
            dict[str, str], raw["successful_fixture_expected_provenance"]
        )
        self._entries = {cast(str, item["fixture_id"]): item for item in fixtures}
        if len(self._entries) != 12:
            raise ValueError("fixture manifest must contain exactly twelve unique fixtures")

    def entries(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._entries.values())

    def entry(self, fixture_id: str) -> dict[str, Any]:
        return self._entries[fixture_id]


class FixtureCallSource:
    adapter_name = "fixture-call-source"
    adapter_version = "fixture-call-source-v1"

    def __init__(self, manifest: FixtureManifest | None = None) -> None:
        self.manifest = manifest or FixtureManifest()

    def events(self, fixture_id: str | None = None) -> tuple[IngestionEvent, ...]:
        entries = (
            (self.manifest.entry(fixture_id),)
            if fixture_id is not None
            else self.manifest.entries()
        )
        events: list[IngestionEvent] = []
        for entry in entries:
            payload = {
                "fixture_id": entry["fixture_id"],
                "received_at": entry["event"]["received_at"],
                "call": entry["event"]["call"],
            }
            events.append(IngestionEvent.model_validate_json(json.dumps(payload)))
        return tuple(events)


class FixtureTranscriber:
    adapter_name = "fixture-transcriber"
    adapter_version = "fixture-transcriber-v1"
    model_version = "deterministic-transcript-v1"

    def __init__(self, manifest: FixtureManifest | None = None) -> None:
        self.manifest = manifest or FixtureManifest()

    def transcribe(
        self,
        call: NormalizedCall,
        *,
        fixture_id: str,
        call_id: str,
        attempt_number: int,
        provenance: Provenance,
    ) -> Transcript:
        del call
        entry = self.manifest.entry(fixture_id)
        failures = cast(list[dict[str, Any]], entry.get("transcriber_failures", []))
        for failure in failures:
            if int(failure["attempt_number"]) == attempt_number:
                raise FixtureAdapterError(
                    failure_class=cast(str, failure["failure_class"]),
                    terminal_state=cast(str, failure["terminal_state"]),
                    diagnostic_code=cast(str, failure["diagnostic_code"]),
                    retryable=cast(bool, failure["retryable"]),
                )
        transcript = cast(dict[str, Any], entry["transcript"])
        segments: list[dict[str, Any]] = []
        for raw_segment in cast(list[dict[str, Any]], transcript["segments"]):
            speaker = cast(str, raw_segment["speaker"])
            segment = dict(raw_segment)
            segment["identity"] = {
                "speaker": speaker,
                "asserted_label": None,
                "verification_state": "unknown"
                if speaker == "unknown_participant"
                else "unverified",
            }
            segments.append(segment)
        payload = {
            "transcript_id": _deterministic_id("transcript", fixture_id),
            "call_id": call_id,
            "language": transcript["language"],
            "diarization_status": transcript["diarization_status"],
            "segments": segments,
            "provenance": provenance.model_dump(mode="json"),
        }
        return Transcript.model_validate_json(json.dumps(payload, ensure_ascii=False))


class FixtureAnalyzer:
    adapter_name = "fixture-analyzer"
    adapter_version = "fixture-analyzer-v1"
    model_version = "deterministic-analysis-v1"
    prompt_version = "facts-first-prompt-v1"

    def __init__(self, manifest: FixtureManifest | None = None) -> None:
        self.manifest = manifest or FixtureManifest()

    @staticmethod
    def _evidence(segment_ids: list[str], transcript: Transcript) -> tuple[EvidenceReference, ...]:
        by_id = {segment.segment_id: segment for segment in transcript.segments}
        return tuple(
            EvidenceReference(
                segment_id=by_id[segment_id].segment_id,
                start_seconds=by_id[segment_id].start_seconds,
                end_seconds=by_id[segment_id].end_seconds,
                speaker=by_id[segment_id].speaker,
                excerpt=by_id[segment_id].text,
            )
            for segment_id in segment_ids
        )

    def _text_fact(self, raw: dict[str, Any], transcript: Transcript) -> TextFact:
        return TextFact(
            state=ValueState(cast(str, raw["state"])),
            value=cast(str | None, raw.get("value")),
            evidence=self._evidence(cast(list[str], raw.get("evidence", [])), transcript),
        )

    def _date(self, raw: dict[str, Any], transcript: Transcript) -> DateFact:
        return DateFact(
            state=ValueState(cast(str, raw["state"])),
            expression=cast(str | None, raw.get("expression")),
            iso_date=cast(str | None, raw.get("iso_date")),
            is_deadline=cast(bool, raw.get("is_deadline", False)),
            evidence=self._evidence(cast(list[str], raw.get("evidence", [])), transcript),
        )

    def extract_facts(self, fixture_id: str, transcript: Transcript) -> ExtractedFacts:
        raw = cast(dict[str, Any], self.manifest.entry(fixture_id)["expected_facts"])
        commitments: list[StaffCommitment] = []
        for item in cast(list[dict[str, Any]], raw["staff_commitments"]):
            timing_raw = cast(dict[str, Any] | None, item.get("timing"))
            commitments.append(
                StaffCommitment(
                    state=cast(Any, ValueState(cast(str, item["state"]))),
                    commitment=cast(str | None, item.get("commitment")),
                    responsible_role=ResponsibleRole(cast(str, item["responsible_role"])),
                    timing=self._date(timing_raw, transcript) if timing_raw else None,
                    evidence=self._evidence(cast(list[str], item.get("evidence", [])), transcript),
                )
            )
        payload = ExtractedFacts(
            caller_request=self._text_fact(cast(dict[str, Any], raw["caller_request"]), transcript),
            reported_facts=tuple(
                self._text_fact(item, transcript)
                for item in cast(list[dict[str, Any]], raw["reported_facts"])
            ),
            people_or_organizations=tuple(
                self._text_fact(item, transcript)
                for item in cast(list[dict[str, Any]], raw["people_or_organizations"])
            ),
            dates=tuple(
                self._date(item, transcript) for item in cast(list[dict[str, Any]], raw["dates"])
            ),
            appointments=tuple[AppointmentFact, ...](),
            monetary_figures=tuple[MonetaryFigure, ...](),
            staff_commitments=tuple(commitments),
            requested_follow_up=self._text_fact(
                cast(dict[str, Any], raw["requested_follow_up"]), transcript
            ),
            unresolved_questions=tuple(
                UnresolvedQuestion(
                    question=cast(str, item["question"]),
                    state=cast(Any, ValueState(cast(str, item["state"]))),
                    evidence=self._evidence(cast(list[str], item.get("evidence", [])), transcript),
                )
                for item in cast(list[dict[str, Any]], raw["unresolved_questions"])
            ),
            missing_context=tuple(cast(list[str], raw["missing_context"])),
            caller_identity=IdentityClaim(
                state=cast(Any, ValueState(cast(str, raw["caller_identity_state"]))),
                label=None,
                metadata_verified=False,
            ),
            confidence=Confidence(cast(str, raw["confidence"])),
        )
        return ExtractedFacts.model_validate_json(payload.model_dump_json())

    def apply_playbook(
        self,
        fixture_id: str,
        *,
        call_id: str,
        facts: ExtractedFacts,
        transcript: Transcript,
        provenance: Provenance,
    ) -> StructuredAnalysis:
        raw = cast(dict[str, Any], self.manifest.entry(fixture_id)["expected_analysis"])
        payload = {
            key: value
            for key, value in raw.items()
            if key not in {"terminal_state", "attempt_count", "disposition", "assertion_count"}
        }
        for collection in (
            "attorney_attention_issues",
            "dissatisfaction_indicators",
            "omitted_information_findings",
            "findings",
        ):
            converted: list[dict[str, Any]] = []
            for finding in cast(list[dict[str, Any]], payload[collection]):
                item = dict(finding)
                item["evidence"] = [
                    evidence.model_dump(mode="json")
                    for evidence in self._evidence(
                        cast(list[str], finding.get("evidence", [])), transcript
                    )
                ]
                converted.append(item)
            payload[collection] = converted
        payload.update(
            {
                "analysis_id": _deterministic_id("analysis", fixture_id),
                "call_id": call_id,
                "acceptance_state": AnalysisAcceptanceState.ACCEPTED.value,
                "advisory_status": AdvisoryStatus.ADVISORY.value,
                "facts": facts.model_dump(mode="json"),
                "provenance": provenance.model_dump(mode="json"),
            }
        )
        return StructuredAnalysis.model_validate_json(json.dumps(payload, ensure_ascii=False))
