"""Execute the single bounded Slice 3B run after a fresh passing preflight."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from packages.config import AppProfile, Settings
from packages.contracts.media import MediaInspectionResult, TemporaryObjectReference
from packages.contracts.review import (
    CallSource,
    Direction,
    NormalizedCall,
    Provenance,
    Speaker,
    Transcript,
)
from packages.generated_audio_scripts import (
    ENGLISH_LONG_A_TEXT,
    ENGLISH_LONG_B_TEXT,
    ENGLISH_SHORT_TEXT,
    SPANISH_SHORT_TEXT,
)
from packages.media import LocalSyntheticObjectStore, MediaInspector, MediaNormalizer
from packages.transcription import TranscriptionAdapterError, create_live_openai_transcriber
from packages.transcription.live import (
    APPROVED_ASSET_IDS,
    PREFLIGHT_TTL_SECONDS,
    LiveRunBudget,
    asset_fingerprint,
    live_gate_failures,
)

SLICE_ROOT = Path("/tmp/colacci-law-slice3b")  # nosec B108
ASSET_ROOT = SLICE_ROOT / "generated"
OBJECT_ROOT = SLICE_ROOT / "objects"
REPORT_ROOT = SLICE_ROOT / "reports"
MANIFEST_PATH = SLICE_ROOT / "generated-manifest.json"
PREFLIGHT_PATH = REPORT_ROOT / "slice3b-live-preflight.json"
EVIDENCE_PATH = REPORT_ROOT / "slice3b-live-evidence.json"
OPERATIONS_LOG = REPORT_ROOT / "slice3b-live-operations.log"
DATABASE_PATH = SLICE_ROOT / "slice3b-live.sqlite3"

EXPECTED_TEXT = {
    "english-short": ENGLISH_SHORT_TEXT,
    "spanish-short": SPANISH_SHORT_TEXT,
    "english-long": f"{ENGLISH_LONG_A_TEXT} {ENGLISH_LONG_B_TEXT}",
}
EXPECTED_PHRASES = {
    "english-short": ("packet can be reviewed", "no real person"),
    "spanish-short": ("lista de documentos", "persona real"),
    "english-long": (
        "document checklist",
        "different synthetic participant",
        "no real client",
    ),
}


class Resolver:
    def __init__(
        self,
        reference: TemporaryObjectReference,
        inspection: MediaInspectionResult,
        path: Path,
    ) -> None:
        self.item = (reference, inspection, path)

    def resolve_media(
        self, media_reference: str
    ) -> tuple[TemporaryObjectReference, MediaInspectionResult, object]:
        if media_reference != "approved-generated-media":
            raise ValueError("unapproved_media_reference")
        return self.item


def _identifier(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:32]


def _words(value: str) -> list[str]:
    return re.findall(r"[^\W_]+", value.casefold(), flags=re.UNICODE)


def _characters(value: str) -> list[str]:
    return list("".join(_words(value)))


def _distance(expected: list[str], actual: list[str]) -> int:
    previous = list(range(len(actual) + 1))
    for expected_item in expected:
        current = [previous[0] + 1]
        for index, actual_item in enumerate(actual, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[index] + 1,
                    previous[index - 1] + int(expected_item != actual_item),
                )
            )
        previous = current
    return previous[-1]


def _quality(asset_id: str, transcript: Transcript) -> dict[str, object]:
    expected = EXPECTED_TEXT[asset_id]
    actual = transcript.original_language_text or ""
    expected_words = _words(expected)
    actual_words = _words(actual)
    expected_characters = _characters(expected)
    actual_characters = _characters(actual)
    expected_vocabulary = set(expected_words)
    invented = [word for word in actual_words if word not in expected_vocabulary]
    normalized_actual = " ".join(actual_words)
    present_phrases = [
        phrase for phrase in EXPECTED_PHRASES[asset_id] if phrase in normalized_actual
    ]
    missing_phrases = [
        phrase for phrase in EXPECTED_PHRASES[asset_id] if phrase not in normalized_actual
    ]
    labels = {
        segment.identity.raw_provider_speaker_label
        for segment in transcript.segments
        if segment.identity.raw_provider_speaker_label is not None
    }
    timestamps_valid = all(
        segment.start_seconds is not None
        and segment.end_seconds is not None
        and segment.start_seconds < segment.end_seconds
        for segment in transcript.segments
    )
    return {
        "normalized_word_error_rate": round(
            _distance(expected_words, actual_words) / max(1, len(expected_words)), 4
        ),
        "character_error_rate": round(
            _distance(expected_characters, actual_characters) / max(1, len(expected_characters)),
            4,
        ),
        "materially_invented_word_count": len(invented),
        "expected_substantive_phrases_present": present_phrases,
        "expected_substantive_phrases_missing": missing_phrases,
        "detected_language": transcript.language,
        "segment_count": len(transcript.segments),
        "provider_speaker_label_count": len(labels),
        "all_identities_unknown_participant": all(
            segment.speaker is Speaker.UNKNOWN_PARTICIPANT for segment in transcript.segments
        ),
        "timestamps_valid": timestamps_valid,
        "diarization_observation": (
            "multiple_labels_observed" if len(labels) > 1 else "single_label_observed"
        ),
    }


def _validate_preflight() -> dict[str, Any]:
    report = cast(dict[str, Any], json.loads(PREFLIGHT_PATH.read_text(encoding="utf-8")))
    checked_at = datetime.fromisoformat(str(report["checked_at"]))
    age = (datetime.now(UTC) - checked_at).total_seconds()
    if report.get("status") != "pass" or age < 0 or age > PREFLIGHT_TTL_SECONDS:
        raise RuntimeError("passing_current_preflight_required")
    if live_gate_failures(os.environ):
        raise RuntimeError("authorization_gate_changed_after_preflight")
    if os.environ.get("TRANSCRIPTION_LIVE_EXECUTION_CONFIRMED") != "true":
        raise RuntimeError("explicit_live_execution_confirmation_required")
    return report


def _provenance(asset_id: str) -> Provenance:
    return Provenance(
        schema_version="review-contracts-v1",
        call_source=CallSource.FIXTURE,
        source_event_id=f"generated-event-{asset_id}",
        source_call_id=f"generated-call-{asset_id}",
        transcript_adapter="openai-transcriber-live",
        transcript_model_version="gpt-4o-transcribe-diarize",
        analysis_adapter="disabled",
        analysis_model_version="disabled-v1",
        prompt_version="not-applicable-v1",
        playbook_version="not-applicable-v1",
        adapter_version="openai-transcriber-live-v1",
        generated_at=datetime.now(UTC),
        processing_attempt_id=_identifier(f"live-attempt:{asset_id}"),
        environment="live_test",
        endpoint_class="official-openai",
        project_configuration="project-scoped-present",
        authorization_reference="OWNER-CHAT-2026-08-17-SLICE-3B",
    )


def _initialize_database() -> sqlite3.Connection:
    DATABASE_PATH.unlink(missing_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.executescript(
        """
        CREATE TABLE attempts (asset_id TEXT, attempt_count INTEGER, status TEXT);
        CREATE TABLE transcripts (asset_id TEXT, transcript_json TEXT, evaluation_json TEXT);
        CREATE TABLE deletions (asset_id TEXT, confirmed INTEGER);
        """
    )
    return connection


def _cleanup_generated() -> None:
    shutil.rmtree(ASSET_ROOT, ignore_errors=True)
    shutil.rmtree(OBJECT_ROOT, ignore_errors=True)
    MANIFEST_PATH.unlink(missing_ok=True)
    (REPORT_ROOT / "generated-audio-report.json").unlink(missing_ok=True)
    DATABASE_PATH.unlink(missing_ok=True)


def _safe_manifest_item(
    asset_id: str, item: dict[str, Any], inspection: MediaInspectionResult
) -> dict[str, object]:
    return {
        "asset_id": asset_id,
        "synthetic": True,
        "kind": str(item["kind"]),
        "duration_seconds": round(inspection.duration_seconds, 3),
        "byte_size": inspection.byte_size,
        "channel_count": inspection.channel_count,
        "language": "es" if asset_id == "spanish-short" else "en",
        "hash_reference": inspection.hash_reference,
        "chunking_strategy": "auto" if inspection.duration_seconds > 30 else "none",
    }


def _validate_operations_log() -> None:
    content = OPERATIONS_LOG.read_text(encoding="utf-8").lower()
    forbidden = (
        "api key",
        "authorization",
        "credential",
        "database",
        "filename",
        "local path",
        "provider",
        "secret",
        "transcript",
        "url",
    )
    if any(item in content for item in forbidden):
        raise RuntimeError("operations_log_content_scan_failed")


def _run(preflight: dict[str, Any]) -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    if settings.app_profile is not AppProfile.LIVE_TEST:
        raise RuntimeError("live_test_profile_required")
    manifest = cast(dict[str, Any], json.loads(MANIFEST_PATH.read_text(encoding="utf-8")))
    assets = {
        str(item["asset_id"]): item for item in cast(list[dict[str, Any]], manifest["assets"])
    }
    source_inspector = MediaInspector(
        max_bytes=settings.media_max_bytes,
        max_duration_seconds=settings.media_max_duration_seconds,
        allowed_root=ASSET_ROOT,
    )
    actual_manifest = [
        _safe_manifest_item(
            asset_id,
            assets[asset_id],
            source_inspector.inspect(
                ASSET_ROOT / str(assets[asset_id]["filename"]),
                artifact_id=_identifier(f"live-artifact:{asset_id}"),
            ),
        )
        for asset_id in APPROVED_ASSET_IDS
    ]
    if asset_fingerprint(actual_manifest) != preflight.get("asset_fingerprint"):
        raise RuntimeError("approved_asset_fingerprint_changed")
    store = LocalSyntheticObjectStore(
        OBJECT_ROOT,
        profile=AppProfile.LIVE_TEST,
        approved_source_root=ASSET_ROOT,
    )
    inspector = MediaInspector(
        max_bytes=settings.media_max_bytes,
        max_duration_seconds=settings.media_max_duration_seconds,
        allowed_root=OBJECT_ROOT,
    )
    normalizer = MediaNormalizer(store=store, inspector=inspector)
    budget = LiveRunBudget()
    connection = _initialize_database()
    evidence_cases: list[dict[str, object]] = []
    operations: list[dict[str, object]] = []
    provider_failures: list[dict[str, object]] = []
    status = "pass"
    failure_class: str | None = None
    try:
        for index, asset_id in enumerate(APPROVED_ASSET_IDS, start=1):
            item = assets[asset_id]
            reference = store.import_file(
                ASSET_ROOT / str(item["filename"]),
                artifact_id=_identifier(f"live-artifact:{asset_id}"),
            )
            normalized_reference = reference
            live_client: object | None = None
            try:
                inspection = inspector.inspect(
                    store.resolve(reference), artifact_id=reference.artifact_id
                )
                normalized_reference, _ = normalizer.normalize(reference, inspection)
                normalized_inspection = inspector.inspect(
                    store.resolve(normalized_reference), artifact_id=reference.artifact_id
                )
                if (
                    _safe_manifest_item(asset_id, item, normalized_inspection)
                    != actual_manifest[index - 1]
                ):
                    raise RuntimeError("uploaded_asset_changed_after_preflight")
                resolver = Resolver(
                    normalized_reference,
                    normalized_inspection,
                    store.resolve(normalized_reference),
                )
                adapter = create_live_openai_transcriber(
                    settings,
                    media_resolver=resolver,
                    request_guard=budget,
                )
                live_client = adapter.client
                call_id = _identifier(f"live-call:{asset_id}")
                call = NormalizedCall(
                    source=CallSource.FIXTURE,
                    source_event_id=f"generated-event-{asset_id}",
                    source_call_id=f"generated-call-{asset_id}",
                    occurred_at=datetime.now(UTC),
                    direction=Direction.UNKNOWN,
                    duration_seconds=normalized_inspection.duration_seconds,
                    language_hint="es" if asset_id == "spanish-short" else "en",
                    media_reference="approved-generated-media",
                    synthetic=True,
                )
                try:
                    transcript = adapter.transcribe(
                        call,
                        fixture_id=f"slice3b-{index}",
                        call_id=call_id,
                        attempt_number=1,
                        provenance=_provenance(asset_id),
                    )
                except TranscriptionAdapterError as exc:
                    provider_failures.append(
                        {
                            "asset_id": asset_id,
                            "error_class": exc.classification.error_class.value,
                            "retryable": exc.classification.retryable,
                            "attempt_count": len(exc.attempts),
                        }
                    )
                    connection.execute(
                        "INSERT INTO attempts VALUES (?, ?, ?)",
                        (asset_id, len(exc.attempts), "failed"),
                    )
                    operations.append({"case_code": f"case-{index:03d}", "status": "failed"})
                    raise
                expected_language = "es" if asset_id == "spanish-short" else "en"
                if transcript.language != expected_language:
                    raise RuntimeError("original_language_not_preserved")
                expected_chunking = "auto" if asset_id == "english-long" else None
                if any(
                    metadata.chunking_strategy != expected_chunking
                    for metadata in adapter.request_metadata
                ):
                    raise RuntimeError("chunking_contract_mismatch")
                budget.record_usage(
                    adapter.response_metadata.usage
                    if adapter.response_metadata is not None
                    else None
                )
                quality = _quality(asset_id, transcript)
                connection.execute(
                    "INSERT INTO attempts VALUES (?, ?, ?)",
                    (asset_id, len(adapter.request_metadata), "success"),
                )
                connection.execute(
                    "INSERT INTO transcripts VALUES (?, ?, ?)",
                    (
                        asset_id,
                        transcript.model_dump_json(),
                        json.dumps(quality, sort_keys=True),
                    ),
                )
                evidence_cases.append(
                    {
                        "asset_id": asset_id,
                        "transcript": transcript.model_dump(mode="json"),
                        "quality": quality,
                        "usage": (
                            adapter.response_metadata.usage.model_dump(mode="json")
                            if adapter.response_metadata is not None
                            and adapter.response_metadata.usage is not None
                            else None
                        ),
                    }
                )
                operations.append({"case_code": f"case-{index:03d}", "status": "success"})
            finally:
                close_client = getattr(live_client, "close", None)
                if callable(close_client):
                    close_client()
                deletion_results = []
                if normalized_reference.object_id != reference.object_id:
                    deletion_results.append(store.delete(normalized_reference))
                deletion_results.append(store.delete(reference))
                deleted = all(item.deletion_confirmed for item in deletion_results)
                connection.execute("INSERT INTO deletions VALUES (?, ?)", (asset_id, int(deleted)))
                if not deleted:
                    raise RuntimeError("temporary_media_deletion_failed")
    except Exception as exc:
        status = "failed"
        failure_class = type(exc).__name__
        raise
    finally:
        connection.commit()
        remaining = len(list(OBJECT_ROOT.iterdir())) if OBJECT_ROOT.exists() else 0
        OPERATIONS_LOG.write_text(
            "".join(json.dumps(item, sort_keys=True) + "\n" for item in operations),
            encoding="utf-8",
        )
        _validate_operations_log()
        connection.close()
        DATABASE_PATH.unlink(missing_ok=True)
        database_disposed = not DATABASE_PATH.exists()
        report = {
            "version": "slice3b-live-evidence-v1",
            "status": status,
            "failure_class": failure_class,
            "authorization_reference": "OWNER-CHAT-2026-08-17-SLICE-3B",
            "endpoint": preflight.get("endpoint"),
            "model": "gpt-4o-transcribe-diarize",
            "response_format": "diarized_json",
            "project_configuration": "project-scoped-accepted" if status == "pass" else "present",
            "cases": evidence_cases,
            "safe_provider_failures": provider_failures,
            "manifest": actual_manifest,
            "counters": budget.safe_report(),
            "cost_basis": (
                "application-side conservative reservation; provider usage recorded when returned"
            ),
            "analysis_request_count": 0,
            "temporary_media_remaining": remaining,
            "deletion_confirmed": remaining == 0,
            "isolated_database_disposed": database_disposed,
            "operations_log_content_scan": "pass",
        }
        EVIDENCE_PATH.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.chmod(EVIDENCE_PATH, 0o600)
        os.chmod(OPERATIONS_LOG, 0o600)
    print(
        f"transcription-live pass: requests={budget.request_count} retries={budget.retry_count} "
        f"retained_media=0 reserved_cost_usd={budget.reserved_cost_usd}"
    )


def main() -> None:
    try:
        _run(_validate_preflight())
    finally:
        _cleanup_generated()


if __name__ == "__main__":
    main()
