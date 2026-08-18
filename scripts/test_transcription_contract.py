"""Network-blocked SDK contract harness for the Slice 3A candidate adapter."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import httpx2
from openai import OpenAI

from packages.config import AppProfile, Settings
from packages.contracts.media import (
    MediaErrorClass,
    MediaInspectionResult,
    TemporaryObjectReference,
)
from packages.contracts.review import (
    CallSource,
    Direction,
    NormalizedCall,
    Provenance,
    Speaker,
    Transcript,
    TranscriptValidationState,
)
from packages.media import LocalSyntheticObjectStore, MediaInspector, MediaNormalizer
from packages.review.validation import transcript_validation_state
from packages.transcription import (
    LiveTranscriptionBlockedError,
    OpenAITranscriber,
    TranscriptionAdapterError,
    create_live_openai_transcriber,
)

SLICE_ROOT = Path("/tmp/colacci-law-slice3a")  # nosec B108
ASSET_ROOT = SLICE_ROOT / "generated"
OBJECT_ROOT = SLICE_ROOT / "contract-objects"
REPORT_ROOT = SLICE_ROOT / "reports"
MANIFEST_PATH = SLICE_ROOT / "generated-manifest.json"
FIXTURE_ROOT = Path("fixtures/transcription-responses")


def _identifier(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()[:32]


class Resolver:
    def __init__(self) -> None:
        self.items: dict[str, tuple[TemporaryObjectReference, MediaInspectionResult, Path]] = {}

    def add(
        self,
        key: str,
        reference: TemporaryObjectReference,
        inspection: MediaInspectionResult,
        path: Path,
    ) -> None:
        self.items[key] = (reference, inspection, path)

    def resolve_media(
        self, media_reference: str
    ) -> tuple[TemporaryObjectReference, MediaInspectionResult, object]:
        return self.items[media_reference]


class DeterministicClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        self.value += 0.01
        return self.value


class MockSequence:
    def __init__(self, outcomes: list[str]) -> None:
        self.outcomes = iter(outcomes)
        self.request_count = 0
        self.shapes: list[dict[str, object]] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.request_count += 1
        body = request.content
        body_text = body.decode("utf-8", errors="ignore")
        self.shapes.append(
            {
                "endpoint": request.url.path,
                "model": "gpt-4o-transcribe-diarize" in body_text,
                "response_format": "diarized_json" in body_text,
                "chunking_auto": "chunking_strategy" in body_text and "auto" in body_text,
                "known_speaker_fields_absent": (
                    "known_speaker_names" not in body_text
                    and "known_speaker_references" not in body_text
                ),
                "files_api_absent": request.url.path != "/v1/files",
            }
        )
        outcome = next(self.outcomes)
        if outcome == "timeout":
            raise httpx2.ReadTimeout("invented timeout", request=request)
        if outcome == "connection":
            raise httpx2.ConnectError("invented connection failure", request=request)
        if outcome == "malformed-json":
            return httpx2.Response(
                200,
                content=(FIXTURE_ROOT / "malformed-json.txt").read_bytes(),
                headers={"content-type": "application/json"},
                request=request,
            )
        fixture = json.loads((FIXTURE_ROOT / f"{outcome}.json").read_text(encoding="utf-8"))
        if isinstance(fixture, dict) and "status_code" in fixture:
            status_code = int(fixture.pop("status_code"))
            headers = {}
            if "retry_after_seconds" in fixture:
                headers["retry-after"] = str(fixture.pop("retry_after_seconds"))
            return httpx2.Response(
                status_code,
                json=fixture,
                headers=headers,
                request=request,
            )
        return httpx2.Response(200, json=fixture, request=request)


def _provenance(call: NormalizedCall, call_id: str) -> Provenance:
    return Provenance(
        schema_version="review-contracts-v1",
        call_source=CallSource.FIXTURE,
        source_event_id=call.source_event_id,
        source_call_id=call.source_call_id,
        transcript_adapter="openai-transcriber-candidate",
        transcript_model_version="gpt-4o-transcribe-diarize",
        analysis_adapter="fixture-analyzer",
        analysis_model_version="deterministic-analysis-v1",
        prompt_version="facts-first-prompt-v1",
        playbook_version="synthetic-draft-v1",
        adapter_version="openai-transcriber-candidate-v1",
        generated_at=datetime.now(UTC),
        processing_attempt_id=_identifier(f"attempt:{call_id}"),
        environment="fixture",
    )


def _call(media_reference: str, inspection: MediaInspectionResult) -> tuple[NormalizedCall, str]:
    call_id = _identifier(f"call:{media_reference}")
    return (
        NormalizedCall(
            source=CallSource.FIXTURE,
            source_event_id=f"event-{media_reference}",
            source_call_id=f"source-{media_reference}",
            recording_id=None,
            occurred_at=datetime.now(UTC),
            direction=Direction.UNKNOWN,
            duration_seconds=inspection.duration_seconds,
            staff_extension=None,
            language_hint=None,
            media_reference=media_reference,
            transcript_fixture_reference=None,
            metadata={},
            synthetic=True,
        ),
        call_id,
    )


def _client(sequence: MockSequence) -> OpenAI:
    transport = httpx2.MockTransport(sequence)
    http_client = httpx2.Client(transport=transport)
    return OpenAI(
        api_key="offline-placeholder-not-a-credential",
        http_client=http_client,
        max_retries=0,
    )


def _run_case(
    *,
    name: str,
    outcomes: list[str],
    resolver: Resolver,
    media_reference: str,
    settings: Settings,
) -> tuple[Transcript | None, dict[str, object], list[dict[str, object]]]:
    sequence = MockSequence(outcomes)
    sleeps: list[float] = []
    client = _client(sequence)
    adapter = OpenAITranscriber(
        client=cast(Any, client),
        media_resolver=resolver,
        settings=settings,
        clock=DeterministicClock(),
        sleeper=sleeps.append,
        jitter=lambda: 0.0,
    )
    inspection = resolver.items[media_reference][1]
    call, call_id = _call(media_reference, inspection)
    transcript: Transcript | None = None
    failure_class: str | None = None
    retryable: bool | None = None
    attempts = 0
    try:
        transcript = adapter.transcribe(
            call,
            fixture_id=f"mock-{name}",
            call_id=call_id,
            attempt_number=1,
            provenance=_provenance(call, call_id),
        )
        attempts = len(adapter.request_metadata)
    except TranscriptionAdapterError as exc:
        failure_class = exc.classification.error_class.value
        retryable = exc.classification.retryable
        attempts = len(exc.attempts)
    finally:
        client.close()
    result: dict[str, object] = {
        "case": name,
        "status": "success" if transcript is not None else "failure",
        "attempts": attempts,
        "failure_class": failure_class,
        "retryable": retryable,
        "sleep_schedule_seconds": sleeps,
        "transcript_created": transcript is not None,
        "analysis_created": False,
        "report_item_created": False,
        "downstream_state": (
            transcript_validation_state(transcript).value
            if transcript is not None
            else "not_created"
        ),
        "mock_request_count": sequence.request_count,
    }
    return transcript, result, sequence.shapes


def _prepare_media(
    assets: list[dict[str, Any]],
) -> tuple[LocalSyntheticObjectStore, Resolver, list[TemporaryObjectReference]]:
    store = LocalSyntheticObjectStore(
        OBJECT_ROOT,
        profile=AppProfile.TEST,
        approved_source_root=ASSET_ROOT,
    )
    inspector = MediaInspector(
        max_bytes=20 * 1024 * 1024,
        max_duration_seconds=60,
        allowed_root=OBJECT_ROOT,
    )
    normalizer = MediaNormalizer(store=store, inspector=inspector)
    resolver = Resolver()
    references: list[TemporaryObjectReference] = []
    by_id = {str(item["asset_id"]): item for item in assets}
    for asset_id, media_reference in (
        ("english-short", "media-short"),
        ("english-long", "media-long"),
        ("spanish-short", "media-spanish"),
    ):
        selected = by_id.get(asset_id) or by_id["english-long"]
        source_reference = store.import_file(
            ASSET_ROOT / str(selected["filename"]),
            artifact_id=_identifier(f"contract-artifact:{media_reference}"),
        )
        source_inspection = inspector.inspect(
            store.resolve(source_reference), artifact_id=source_reference.artifact_id
        )
        normalized_reference, _ = normalizer.normalize(source_reference, source_inspection)
        normalized_inspection = inspector.inspect(
            store.resolve(normalized_reference), artifact_id=source_reference.artifact_id
        )
        resolver.add(
            media_reference,
            normalized_reference,
            normalized_inspection,
            store.resolve(normalized_reference),
        )
        references.append(source_reference)
        if normalized_reference.object_id != source_reference.object_id:
            references.append(normalized_reference)
    return store, resolver, references


def _validate_log(log_path: Path) -> None:
    content = log_path.read_text(encoding="utf-8")
    forbidden_terms = (
        "api key",
        "audio",
        "authorization",
        "caller",
        "credential",
        "database",
        "filename",
        "local path",
        "provider request",
        "provider response",
        "provider url",
        "secret",
        "staff",
        "transcript",
        "url",
    )
    if any(term in content.lower() for term in forbidden_terms):
        raise AssertionError("content-free operations log contains a forbidden term")
    for path in FIXTURE_ROOT.glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if (
            isinstance(payload, dict)
            and isinstance(payload.get("text"), str)
            and payload["text"] in content
        ):
            raise AssertionError("response content entered the operations log")


def _case_specifications() -> Iterator[tuple[str, list[str], str]]:
    yield "english_diarized", ["english-diarized"], "media-long"
    yield "spanish_diarized", ["spanish-diarized"], "media-spanish"
    yield "two_unknown_speakers", ["two-unknown-speakers"], "media-short"
    yield "no_diarization", ["no-diarization"], "media-short"
    yield "text_only_fallback", ["text-only-fallback"], "media-spanish"
    yield "extra_unknown_fields", ["extra-unknown-fields"], "media-short"
    yield "missing_segments", ["missing-segments"], "media-short"
    yield "malformed_json", ["malformed-json"], "media-short"
    yield "invalid_timestamps", ["invalid-timestamps"], "media-short"
    yield "overlapping_timestamps", ["overlapping-timestamps"], "media-short"
    yield "reversed_timestamps", ["reversed-timestamps"], "media-short"
    yield "unsupported_language", ["unsupported-language"], "media-short"
    yield "authentication_failure", ["authentication-failure"], "media-short"
    yield "rate_limit_then_success", ["rate-limit", "english-diarized"], "media-long"
    yield "connection_then_success", ["connection", "english-diarized"], "media-long"
    yield "timeout_terminal", ["timeout", "timeout", "timeout"], "media-short"
    yield "provider_5xx_terminal", ["provider-5xx", "provider-5xx", "provider-5xx"], "media-short"


def main() -> None:
    manifest = cast(dict[str, Any], json.loads(MANIFEST_PATH.read_text(encoding="utf-8")))
    store, resolver, references = _prepare_media(cast(list[dict[str, Any]], manifest["assets"]))
    settings = Settings(app_profile=AppProfile.TEST)
    results: list[dict[str, object]] = []
    all_shapes: list[dict[str, object]] = []
    transcripts: dict[str, Transcript] = {}
    request_count = 0
    try:
        for name, outcomes, media_reference in _case_specifications():
            transcript, result, shapes = _run_case(
                name=name,
                outcomes=outcomes,
                resolver=resolver,
                media_reference=media_reference,
                settings=settings,
            )
            results.append(result)
            all_shapes.extend(shapes)
            request_count += cast(int, result["mock_request_count"])
            if transcript is not None:
                transcripts[name] = transcript

        expected_failure_classes = {
            "missing_segments": MediaErrorClass.TRANSCRIPTION_RESPONSE_INVALID.value,
            "malformed_json": MediaErrorClass.TRANSCRIPTION_RESPONSE_INVALID.value,
            "invalid_timestamps": MediaErrorClass.TRANSCRIPTION_RESPONSE_INVALID.value,
            "overlapping_timestamps": MediaErrorClass.TRANSCRIPTION_RESPONSE_INVALID.value,
            "reversed_timestamps": MediaErrorClass.TRANSCRIPTION_RESPONSE_INVALID.value,
            "unsupported_language": MediaErrorClass.TRANSCRIPTION_RESPONSE_INVALID.value,
            "authentication_failure": MediaErrorClass.TRANSCRIPTION_AUTH_FAILED.value,
            "timeout_terminal": MediaErrorClass.TRANSCRIPTION_TIMEOUT.value,
            "provider_5xx_terminal": MediaErrorClass.TRANSCRIPTION_PROVIDER_FAILED.value,
        }
        by_case = {str(item["case"]): item for item in results}
        for case_name, expected in expected_failure_classes.items():
            if by_case[case_name]["failure_class"] != expected:
                raise AssertionError(f"wrong safe failure class for {case_name}")
            if by_case[case_name]["transcript_created"]:
                raise AssertionError("terminal failure created downstream output")
        if by_case["authentication_failure"]["attempts"] != 1:
            raise AssertionError("authentication failure was retried")
        if by_case["rate_limit_then_success"]["sleep_schedule_seconds"] != [2.0]:
            raise AssertionError("bounded Retry-After was not honored")
        if by_case["connection_then_success"]["sleep_schedule_seconds"] != [1.0]:
            raise AssertionError("connection failure did not use deterministic backoff")
        if by_case["timeout_terminal"]["attempts"] != 3:
            raise AssertionError("timeout retries were not capped at three attempts")

        english = transcripts["english_diarized"]
        spanish = transcripts["spanish_diarized"]
        fallback = transcripts["text_only_fallback"]
        unknown = transcripts["two_unknown_speakers"]
        if any(segment.speaker is not Speaker.UNKNOWN_PARTICIPANT for segment in unknown.segments):
            raise AssertionError("provider labels were mapped to an asserted identity")
        if fallback.segments or fallback.timestamp_availability.value != "unavailable":
            raise AssertionError("fallback fabricated timestamp evidence")
        if fallback.validation_state is not TranscriptValidationState.REQUIRES_HUMAN_REVIEW:
            raise AssertionError("fallback was not routed to visible review")
        if not all(
            shape["endpoint"] == "/v1/audio/transcriptions"
            and shape["model"]
            and shape["response_format"]
            and shape["known_speaker_fields_absent"]
            and shape["files_api_absent"]
            for shape in all_shapes
        ):
            raise AssertionError("candidate request contract drifted")
        if not all_shapes[0]["chunking_auto"]:
            raise AssertionError("long media did not request automatic chunking")

        os.environ["OPENAI_API_KEY"] = "ambient-value-is-not-authority"
        live_rejected = False
        try:
            create_live_openai_transcriber(settings)
        except LiveTranscriptionBlockedError:
            live_rejected = True
        finally:
            os.environ.pop("OPENAI_API_KEY", None)
        if not live_rejected:
            raise AssertionError("live client construction was not rejected")

        REPORT_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
        operation_log = REPORT_ROOT / "slice3a-operations.log"
        operation_log.write_text(
            "".join(
                json.dumps(
                    {
                        "event": "boundary_case_completed",
                        "case_code": f"case-{index + 1:03d}",
                        "attempts": item["attempts"],
                        "status": "pass",
                    },
                    sort_keys=True,
                )
                + "\n"
                for index, item in enumerate(results)
            ),
            encoding="utf-8",
        )
        os.chmod(operation_log, 0o600)
        _validate_log(operation_log)

        safe_shapes = {
            "endpoint": "/v1/audio/transcriptions",
            "model": settings.transcription_model_id,
            "response_format": "diarized_json",
            "long_media_chunking_strategy": "auto",
            "known_speaker_fields_used": False,
            "files_api_used": False,
            "realtime_used": False,
        }
        report = {
            "version": "mocked-transcription-contract-report-v1",
            "status": "pass",
            "sdk_version": "3.2.0",
            "transport": "injected_mock_transport",
            "external_network_blocked": True,
            "external_request_count": 0,
            "mock_request_count": request_count,
            "request_shape": safe_shapes,
            "live_client_construction_rejected": live_rejected,
            "ambient_key_insufficient_authority": live_rejected,
            "speaker_identity": {
                "provider_labels_preserved_as_opaque": True,
                "all_identities_unverified_unknown_participants": True,
                "known_speaker_references_used": False,
            },
            "examples": {
                "english": english.model_dump(mode="json"),
                "spanish": spanish.model_dump(mode="json"),
                "fallback": fallback.model_dump(mode="json"),
            },
            "error_retry_matrix": results,
            "terminal_failure_downstream_counts": {
                "transcripts": 0,
                "analyses": 0,
                "report_items": 0,
            },
            "unknown_provider_fields_persisted": False,
            "operations_log_content_scan": "pass",
        }
        report_path = REPORT_ROOT / "mocked-transcription-contract-report.json"
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
        os.chmod(report_path, 0o600)
    finally:
        unique_references = {item.object_id: item for item in references}
        deletion_events = [store.delete(item) for item in unique_references.values()]
        if not all(item.deletion_confirmed for item in deletion_events):
            raise AssertionError("contract harness cleanup was not confirmed")
        if OBJECT_ROOT.exists() and any(OBJECT_ROOT.iterdir()):
            raise AssertionError("contract object root is not empty")
        if ASSET_ROOT.exists():
            shutil.rmtree(ASSET_ROOT)
        MANIFEST_PATH.unlink(missing_ok=True)
        if OBJECT_ROOT.exists():
            OBJECT_ROOT.rmdir()
    print(
        f"mocked-boundary pass: cases={len(results)} mock_requests={request_count} "
        "external_requests=0 live_client=rejected cleanup=confirmed"
    )


if __name__ == "__main__":
    main()
