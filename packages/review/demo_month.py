"""Deterministic July 2026 transcript-only demonstration month."""

from __future__ import annotations

import json
import random
from collections import Counter
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

from packages.contracts.review import IngestionEvent

MANIFEST_PATH = Path(__file__).parents[2] / "fixtures" / "demo-month" / "manifest.json"


class DemoMonthManifest:
    """Materialize a compact versioned recipe into stable fixture-adapter entries."""

    def __init__(self, path: Path = MANIFEST_PATH) -> None:
        self.contract = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
        self.version = cast(str, self.contract["manifest_version"])
        self.seed = int(self.contract["seed"])
        self._entries = self._build_entries()
        self._validate_contract()

    def entries(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._entries)

    def entry(self, fixture_id: str) -> dict[str, Any]:
        return next(item for item in self._entries if item["fixture_id"] == fixture_id)

    def expected_entries(self, business_date: date | None = None) -> tuple[dict[str, Any], ...]:
        entries = self.entries()
        if business_date is None:
            return entries
        return tuple(item for item in entries if item["business_date"] == str(business_date))

    def received_entries(self) -> tuple[dict[str, Any], ...]:
        return tuple(item for item in self._entries if item["outcome"] != "missing")

    def summary(self) -> dict[str, object]:
        return {
            "manifest_version": self.version,
            "generator_version": self.contract["generator_version"],
            "seed": self.seed,
            "business_month": self.contract["business_month"],
            "totals": self.contract["totals"],
            "categories": self.contract["categories"],
            "languages": self.contract["languages"],
            "scenario_contract": self.contract["scenario_contract"],
        }

    def _build_entries(self) -> list[dict[str, Any]]:
        timezone = ZoneInfo("America/New_York")
        weekdays = [date(2026, 7, day) for day in range(1, 32) if date(2026, 7, day).weekday() < 5]
        volumes = cast(list[int], self.contract["weekday_volumes"])
        slots = [day for day, volume in zip(weekdays, volumes, strict=True) for _ in range(volume)]
        categories = [
            category
            for category, count in cast(dict[str, int], self.contract["categories"]).items()
            for _ in range(count)
        ]
        languages = [
            language
            for language, count in cast(dict[str, int], self.contract["languages"]).items()
            for _ in range(count)
        ]
        rng = random.Random(self.seed)  # noqa: S311  # nosec B311 - fixture ordering only
        rng.shuffle(categories)
        rng.shuffle(languages)

        special: dict[int, tuple[str, ...]] = {
            12: ("evidence_backed_immediate_attention", "confirmed_date_reference"),
            31: ("ambiguous_speakers",),
            44: ("unidentified_third_participant",),
            58: ("incomplete_transcript", "low_confidence_analysis"),
            76: ("relative_unverified_date_reference",),
            103: ("staff_commitment",),
            137: ("retryable_transcription_failure",),
            171: ("cancellation",),
            208: ("retention_eligibility",),
            209: ("successful_deletion",),
            210: ("retryable_deletion_failure",),
            211: ("terminal_deletion_failed",),
        }
        missing_indexes = {222, 477}
        failed_indexes = {89, 149, 199, 249, 299, 349, 399, 449}
        late_indexes = {70, 140, 220, 300, 380, 460}
        duplicate_indexes = {25, 75, 125, 175, 225, 275, 325, 375, 425, 475}
        entries: list[dict[str, Any]] = []
        positions = Counter[date]()
        for offset, (business_date, category, language) in enumerate(
            zip(slots, categories, languages, strict=True), start=1
        ):
            positions[business_date] += 1
            local_hour = 8 + (
                (positions[business_date] - 1) * 9 // max(1, volumes[weekdays.index(business_date)])
            )
            local_minute = ((positions[business_date] - 1) * 17) % 60
            occurred = datetime.combine(
                business_date, time(local_hour, local_minute), tzinfo=timezone
            )
            late = offset in late_indexes
            received = (
                datetime.combine(business_date, time(18, 15), tzinfo=timezone)
                if late
                else occurred + timedelta(seconds=7)
            )
            fixture_id = f"CL-MONTH-202607-{offset:03d}"
            scenarios = list(special.get(offset, ()))
            scenarios.append(
                {
                    "new_intake": "new_consultation",
                    "existing_client_follow_up": "existing_client_follow_up",
                    "administrative": "administrative_request",
                    "routine_no_action": "routine_call",
                    "dissatisfaction_escalation": "dissatisfaction_escalation",
                }[category]
            )
            if language == "es":
                scenarios.append("spanish_intake_and_follow_up")
            if late:
                scenarios.append("late_delivery")
            if offset in duplicate_indexes:
                scenarios.append("duplicate_delivery")
            outcome = (
                "missing"
                if offset in missing_indexes
                else "failed"
                if offset in failed_indexes
                else "analyzed"
            )
            if outcome == "missing":
                scenarios.append("missing_expected_call")
            if offset in failed_indexes:
                scenarios.append("permanent_media_failure")
            entry = self._entry(
                offset=offset,
                fixture_id=fixture_id,
                business_date=business_date,
                occurred=occurred,
                received=received,
                category=category,
                language=language,
                scenarios=tuple(dict.fromkeys(scenarios)),
                outcome=outcome,
            )
            entries.append(entry)
        return entries

    def _entry(
        self,
        *,
        offset: int,
        fixture_id: str,
        business_date: date,
        occurred: datetime,
        received: datetime,
        category: str,
        language: str,
        scenarios: tuple[str, ...],
        outcome: str,
    ) -> dict[str, Any]:
        segment_prefix = f"m{offset:03d}"
        is_partial = "incomplete_transcript" in scenarios
        is_unknown = any(
            scenario in scenarios
            for scenario in ("ambiguous_speakers", "unidentified_third_participant")
        )
        high_attention = (
            category == "dissatisfaction_escalation"
            or "evidence_backed_immediate_attention" in scenarios
        )
        request_en = {
            "new_intake": (
                "I am requesting a new consultation about an entirely invented situation."
            ),
            "existing_client_follow_up": (
                "I am requesting an update about an invented follow-up matter."
            ),
            "administrative": (
                "Please provide the office's approved document-delivery instructions."
            ),
            "routine_no_action": "I am calling only to confirm the published office hours.",
            "dissatisfaction_escalation": (
                "I am dissatisfied because my invented follow-up request has not been answered."
            ),
        }[category]
        request_es = {
            "new_intake": (
                "Solicito una consulta nueva sobre una situación completamente inventada."
            ),
            "existing_client_follow_up": (
                "Solicito una actualización sobre un asunto de seguimiento inventado."
            ),
            "administrative": (
                "Por favor indique las instrucciones aprobadas para entregar documentos."
            ),
            "routine_no_action": (
                "Llamo solamente para confirmar el horario publicado de la oficina."
            ),
            "dissatisfaction_escalation": (
                "Estoy inconforme porque no han respondido a mi solicitud inventada de seguimiento."
            ),
        }[category]
        staff_en = "I will route this invented request to the appropriate review team."
        staff_es = "Enviaré esta solicitud inventada al equipo de revisión correspondiente."
        request = request_es if language == "es" else request_en
        staff = staff_es if language == "es" else staff_en
        segments: list[dict[str, object]] = [
            {
                "segment_id": f"{segment_prefix}-seg-1",
                "speaker": "outside_caller",
                "start_seconds": 2.0,
                "end_seconds": 13.0,
                "text": request,
            },
            {
                "segment_id": f"{segment_prefix}-seg-2",
                "speaker": "staff",
                "start_seconds": 16.0,
                "end_seconds": 27.0,
                "text": staff,
            },
        ]
        if is_unknown:
            segments.append(
                {
                    "segment_id": f"{segment_prefix}-seg-3",
                    "speaker": "unknown_participant",
                    "start_seconds": 30.0,
                    "end_seconds": 37.0,
                    "text": "An unidentified invented participant briefly joined the line.",
                }
            )
        if is_partial:
            segments.append(
                {
                    "segment_id": f"{segment_prefix}-seg-3",
                    "speaker": "unknown_participant",
                    "start_seconds": 30.0,
                    "end_seconds": 38.0,
                    "text": "[invented incomplete transcript segment]",
                }
            )
        date_facts: list[dict[str, object]] = []
        if "confirmed_date_reference" in scenarios:
            segments.append(
                {
                    "segment_id": f"{segment_prefix}-seg-date",
                    "speaker": "outside_caller",
                    "start_seconds": 40.0,
                    "end_seconds": 48.0,
                    "text": "The invented notice confirms July 24, 2026 as the response date.",
                }
            )
            date_facts.append(
                {
                    "state": "present",
                    "expression": "July 24, 2026",
                    "iso_date": "2026-07-24",
                    "is_deadline": True,
                    "evidence": [f"{segment_prefix}-seg-date"],
                }
            )
        elif "relative_unverified_date_reference" in scenarios:
            segments.append(
                {
                    "segment_id": f"{segment_prefix}-seg-date",
                    "speaker": "outside_caller",
                    "start_seconds": 40.0,
                    "end_seconds": 48.0,
                    "text": "Someone mentioned next week, but no date or deadline is confirmed.",
                }
            )
            date_facts.append(
                {
                    "state": "unverified",
                    "expression": "next week",
                    "iso_date": None,
                    "is_deadline": False,
                    "evidence": [f"{segment_prefix}-seg-date"],
                }
            )
        findings = [
            {
                "finding_id": f"{segment_prefix}-finding",
                "kind": "supported_request",
                "statement": (
                    "The invented caller made the request shown in the linked transcript segment."
                ),
                "material": True,
                "evidence": [f"{segment_prefix}-seg-1"],
            }
        ]
        attention = findings if high_attention else []
        dissatisfaction = findings if category == "dissatisfaction_escalation" else []
        general_findings = [] if high_attention else findings
        failures: list[dict[str, object]] = []
        if outcome == "failed":
            failures = [
                {
                    "attempt_number": 1,
                    "failure_class": "invalid_media",
                    "terminal_state": "AUDIO_INVALID",
                    "diagnostic_code": "demo_month_media_permanent",
                    "retryable": False,
                }
            ]
        elif "retryable_transcription_failure" in scenarios:
            failures = [
                {
                    "attempt_number": 1,
                    "failure_class": "transcriber_unavailable",
                    "terminal_state": "TRANSCRIPTION_FAILED",
                    "diagnostic_code": "demo_month_retryable",
                    "retryable": True,
                }
            ]
        confidence = "low" if is_partial else "high" if not is_unknown else "medium"
        return {
            "fixture_id": fixture_id,
            "business_date": str(business_date),
            "category": category,
            "language": language,
            "outcome": outcome,
            "scenarios": list(scenarios),
            "event": {
                "received_at": received.isoformat(),
                "call": {
                    "source": "transcript_only",
                    "source_event_id": f"evt-{fixture_id.lower()}",
                    "source_call_id": f"call-{fixture_id.lower()}",
                    "recording_id": None,
                    "occurred_at": occurred.isoformat(),
                    "direction": "outbound" if offset % 5 == 0 else "inbound",
                    "duration_seconds": 52.0,
                    "staff_extension": f"SYN-{100 + (offset % 8):03d}",
                    "language_hint": language,
                    "media_reference": None,
                    "transcript_fixture_reference": f"transcript-{fixture_id.lower()}",
                    "metadata": {
                        "source_mode": "transcript_only",
                        "manifest_version": self.version,
                        "scenario": ",".join(scenarios),
                        "expected_category": category,
                        "expected_language": language,
                    },
                    "synthetic": True,
                },
            },
            "transcript": {
                "language": language,
                "diarization_status": "partial" if is_partial or is_unknown else "available",
                "segments": segments,
            },
            "expected_facts": {
                "caller_request": {
                    "state": "present",
                    "value": "Invented request retained without adding unsupported facts.",
                    "evidence": [f"{segment_prefix}-seg-1"],
                },
                "reported_facts": [],
                "people_or_organizations": [],
                "dates": date_facts,
                "staff_commitments": [
                    {
                        "state": "present",
                        "commitment": "Route the invented request to the appropriate review team.",
                        "responsible_role": "case_team",
                        "timing": None,
                        "evidence": [f"{segment_prefix}-seg-2"],
                    }
                ],
                "requested_follow_up": {
                    "state": "present",
                    "value": "Human review of the invented request.",
                    "evidence": [f"{segment_prefix}-seg-1"],
                },
                "unresolved_questions": (
                    [
                        {
                            "question": "Speaker identity or missing content remains unresolved.",
                            "state": "unknown",
                            "evidence": [f"{segment_prefix}-seg-3"],
                        }
                    ]
                    if is_partial or is_unknown
                    else []
                ),
                "missing_context": (
                    [
                        "The invented transcript is intentionally incomplete or speaker identity "
                        "is unknown."
                    ]
                    if is_partial or is_unknown
                    else []
                ),
                "caller_identity_state": "unknown" if is_partial or is_unknown else "unverified",
                "confidence": confidence,
            },
            "expected_analysis": {
                "category": category,
                "priority": "immediate"
                if "evidence_backed_immediate_attention" in scenarios
                else "high"
                if high_attention
                else "low"
                if category == "routine_no_action"
                else "normal",
                "summary": (
                    "An invented transcript-only call contains a supported request for "
                    "human review."
                ),
                "proposed_next_steps": ["Review the linked invented evidence before any action."],
                "responsible_role": "spanish_speaking_intake"
                if language == "es" and category == "new_intake"
                else "intake_team"
                if category == "new_intake"
                else "supervising_attorney"
                if high_attention
                else "records_coordinator"
                if category == "administrative"
                else "case_team",
                "suggested_response_timing": "Prompt human review is suggested."
                if high_attention
                else None,
                "attorney_attention_issues": attention,
                "dissatisfaction_indicators": dissatisfaction,
                "omitted_information_findings": findings if is_partial or is_unknown else [],
                "findings": general_findings,
                "internal_file_note_draft": (
                    "Synthetic advisory note based only on the linked invented transcript evidence."
                ),
                "confidence": confidence,
            },
            "transcriber_failures": failures,
        }

    def _validate_contract(self) -> None:
        totals = cast(dict[str, int], self.contract["totals"])
        if len(self._entries) != totals["expected"]:
            raise ValueError("demo month expected total does not match generated entries")
        if len(self.received_entries()) != totals["received"]:
            raise ValueError("demo month received total does not reconcile")
        outcomes = Counter(str(item["outcome"]) for item in self._entries)
        if outcomes != Counter(
            analyzed=totals["analyzed"], failed=totals["failed"], missing=totals["missing"]
        ):
            raise ValueError("demo month outcomes do not match the versioned contract")
        if Counter(str(item["category"]) for item in self._entries) != Counter(
            self.contract["categories"]
        ):
            raise ValueError("demo month category totals do not match")
        if Counter(str(item["language"]) for item in self._entries) != Counter(
            self.contract["languages"]
        ):
            raise ValueError("demo month language totals do not match")


class DemoMonthCallSource:
    adapter_name = "demo-month-transcript-only-source"
    adapter_version = "full-month-transcript-only-v1"

    def __init__(self, manifest: DemoMonthManifest | None = None) -> None:
        self.manifest = manifest or DemoMonthManifest()

    def events(self, fixture_id: str | None = None) -> tuple[IngestionEvent, ...]:
        entries = (
            (self.manifest.entry(fixture_id),)
            if fixture_id is not None
            else self.manifest.received_entries()
        )
        return tuple(
            IngestionEvent.model_validate_json(
                json.dumps({"fixture_id": item["fixture_id"], **item["event"]})
            )
            for item in entries
        )
