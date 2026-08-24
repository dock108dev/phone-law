"""Single-item local orchestration through the accepted immutable review pipeline."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime, time, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

from packages.config import Settings
from packages.contracts.manual_upload import (
    DeterministicOutcome,
    UploadKind,
    UploadMetadata,
    UploadState,
    UploadValidationSummary,
)
from packages.contracts.media import (
    MediaContentType,
    SupportedMediaFormat,
    TemporaryObjectReference,
)
from packages.contracts.report import DemoPrincipal
from packages.contracts.review import (
    SCHEMA_VERSION,
    CallSource,
    FailureClass,
    IngestionEvent,
    NormalizedCall,
    ProcessingState,
    Provenance,
    SanitizedProcessingFailure,
    Transcript,
    TranscriptionTransportProvenance,
)
from packages.database.manual_uploads import (
    CreateReceiptResult,
    ManualUploadRepository,
    StoredUpload,
    upload_identifier,
)
from packages.database.repository import ReviewRepository
from packages.database.review_experience import ReviewExperienceRepository
from packages.manual_upload.manifest import SyntheticFingerprintManifest, SyntheticManifestError
from packages.manual_upload.request_boundary import ParsedAudioUpload, UploadRequestError
from packages.media.processing import MediaBoundaryError, MediaInspector, MediaNormalizer
from packages.media.store import LocalSyntheticObjectStore, SyntheticObjectStoreError
from packages.observability.logging import OperationalLogger
from packages.review.fixtures import FixtureAnalyzer, FixtureTranscriber
from packages.review.transcript_import import (
    TRANSCRIPT_ONLY_ARTIFACT_VERSION,
    TranscriptOnlyArtifact,
    TranscriptOnlyImporter,
    parse_transcript_only_artifact,
)
from packages.review.validation import validate_analysis

MANUAL_AUDIO_CONTRACT = "manual-upload-synthetic-audio-v1"
MANUAL_AUDIO_MODEL = "deterministic-fingerprint-fixture-v1"


class ManualUploadUnexpectedError(RuntimeError):
    """An unexpected defect was persisted as a safe receipt state before escalation."""


class ManualUploadService:
    def __init__(
        self,
        settings: Settings,
        engine: Any,
        *,
        operational_logger: OperationalLogger | None = None,
        correlation_id: str | None = None,
    ) -> None:
        self.settings = settings
        self.receipts = ManualUploadRepository(engine)
        self.reviews = ReviewRepository(engine)
        self.experience = ReviewExperienceRepository(engine)
        self.store = LocalSyntheticObjectStore(
            settings.manual_upload_root,
            profile=settings.app_profile,
        )
        self.inspector = MediaInspector(
            max_bytes=settings.media_max_bytes,
            max_duration_seconds=settings.media_max_duration_seconds,
            allowed_root=self.store.root,
        )
        self.normalizer = MediaNormalizer(store=self.store, inspector=self.inspector)
        self.transcriber = FixtureTranscriber()
        self.analyzer = FixtureAnalyzer()
        self.operational_logger = operational_logger
        self.correlation_id = correlation_id

    def submit_audio(
        self,
        parsed: ParsedAudioUpload,
        *,
        principal: DemoPrincipal,
    ) -> CreateReceiptResult:
        self._validate_timestamp(parsed.metadata)
        artifact_id = upload_identifier("artifact", parsed.metadata.client_submission_id)
        source_reference: TemporaryObjectReference | None = None
        retained_reference: TemporaryObjectReference | None = None
        try:
            source_reference, path = self.store.allocate(artifact_id=artifact_id)
            with path.open("wb") as destination:
                destination.write(parsed.payload)
            os.chmod(path, 0o600)
            inspection = self.inspector.inspect(path, artifact_id=artifact_id)
            self._validate_declared_media(parsed, inspection.media_format, inspection.content_type)
            if (
                inspection.channel_count not in {1, 2}
                or not 8000 <= inspection.sample_rate_hz <= 48000
            ):
                raise UploadRequestError("unsupported_media_shape")
            manifest_entry = SyntheticFingerprintManifest(
                self.settings.manual_upload_manifest_path
            ).entry(inspection.content_sha256)
            expected_language = "es" if manifest_entry.fixture_id == "CL-FX-003" else "en"
            if parsed.metadata.language_hint != expected_language:
                raise UploadRequestError("declared_language_mismatch")
            retained_reference, normalization = self.normalizer.normalize(
                source_reference, inspection
            )
            if retained_reference.object_id != source_reference.object_id:
                deletion = self.store.delete(source_reference)
                if not deletion.deletion_confirmed:
                    self.store.delete(retained_reference)
                    raise UploadRequestError("temporary_media_deletion_failed", status_code=500)
                source_reference = None
            validation = UploadValidationSummary(
                kind=UploadKind.SYNTHETIC_AUDIO,
                contract_version=MANUAL_AUDIO_CONTRACT,
                byte_size=inspection.byte_size,
                duration_seconds=inspection.duration_seconds,
                media_format=inspection.media_format.value,
                channel_count=normalization.channel_count,
                sample_rate_hz=normalization.sample_rate_hz,
            )
            created = self.receipts.create(
                metadata=parsed.metadata,
                kind=UploadKind.SYNTHETIC_AUDIO,
                content_fingerprint=inspection.content_sha256,
                validation=validation,
                principal=principal,
                object_id=retained_reference.object_id,
                artifact_id=artifact_id,
            )
            if created.duplicate:
                deletion = self.store.delete(retained_reference)
                if not deletion.deletion_confirmed:
                    raise UploadRequestError("temporary_media_deletion_failed", status_code=500)
            return created
        except MediaBoundaryError as exc:
            self._delete_references(source_reference, retained_reference)
            raise UploadRequestError(exc.error_class.value.lower()) from exc
        except (SyntheticObjectStoreError, SyntheticManifestError) as exc:
            self._delete_references(source_reference, retained_reference)
            raise UploadRequestError(str(exc)) from exc
        except Exception:
            self._delete_references(source_reference, retained_reference)
            raise

    def submit_transcript(
        self,
        payload: bytes,
        *,
        metadata: UploadMetadata,
        principal: DemoPrincipal,
    ) -> CreateReceiptResult:
        self._validate_timestamp(metadata)
        try:
            artifact = parse_transcript_only_artifact(payload)
        except ValueError as exc:
            raise UploadRequestError("invalid_transcript_artifact") from exc
        call = artifact.event.call
        if (
            call.direction is not metadata.direction
            or call.occurred_at != metadata.captured_at
            or call.language_hint != metadata.language_hint
            or call.staff_extension != metadata.staff_extension
        ):
            raise UploadRequestError("transcript_metadata_mismatch")
        fingerprint = hashlib.sha256(payload).hexdigest()
        validation = UploadValidationSummary(
            kind=UploadKind.TRANSCRIPT_ONLY,
            contract_version=TRANSCRIPT_ONLY_ARTIFACT_VERSION,
            byte_size=len(payload),
            duration_seconds=call.duration_seconds,
            segment_count=len(artifact.transcript.segments),
        )
        created = self.receipts.create(
            metadata=metadata,
            kind=UploadKind.TRANSCRIPT_ONLY,
            content_fingerprint=fingerprint,
            validation=validation,
            principal=principal,
            object_id=None,
            artifact_id=None,
        )
        if not created.duplicate and created.stored.receipt.state is UploadState.READY:
            claimed = self.receipts.claim_processing(created.stored.receipt.upload_id)
            try:
                final = self._process_transcript(claimed, artifact)
            except Exception as exc:
                self.receipts.complete(
                    claimed.receipt.upload_id,
                    state=UploadState.ANALYSIS_FAILED,
                    diagnostic_code="transcript_processing_failed",
                    retryable=False,
                )
                self._record_unexpected_failure("unexpected_transcript_processing_failure")
                raise ManualUploadUnexpectedError("transcript_processing_failed") from exc
            return CreateReceiptResult(stored=final, duplicate=False)
        return created

    def process_audio(self, upload_id: str) -> StoredUpload:
        claimed = self.receipts.claim_processing(upload_id)
        if claimed.receipt.state is UploadState.ANALYZED:
            return claimed
        if claimed.receipt.submission_kind is not UploadKind.SYNTHETIC_AUDIO:
            raise ValueError("transcript_receipt_process_forbidden")
        if claimed.object_id is None or claimed.artifact_id is None:
            return self.receipts.complete(
                upload_id,
                state=UploadState.DELETION_FAILED,
                diagnostic_code="temporary_media_unavailable",
                retryable=False,
                deletion_confirmed=False,
            )
        try:
            manifest_entry = SyntheticFingerprintManifest(
                self.settings.manual_upload_manifest_path
            ).entry(claimed.content_fingerprint)
            return self._run_audio_attempt(
                claimed, manifest_entry.fixture_id, manifest_entry.outcome
            )
        except Exception as exc:
            self._unexpected_audio_failure(claimed)
            self._record_unexpected_failure("unexpected_audio_processing_failure")
            raise ManualUploadUnexpectedError("unexpected_processing_failure") from exc

    def cancel(self, upload_id: str) -> StoredUpload:
        stored, changed = self.receipts.cancel(upload_id)
        if not changed:
            return stored
        if stored.object_id is None or stored.artifact_id is None:
            return self.receipts.confirm_cancel_deletion(upload_id, confirmed=True)
        reference = self._reference(stored)
        deletion = self.store.delete(reference)
        return self.receipts.confirm_cancel_deletion(
            upload_id, confirmed=deletion.deletion_confirmed
        )

    def _run_audio_attempt(
        self,
        stored: StoredUpload,
        fixture_id: str,
        outcome: DeterministicOutcome,
    ) -> StoredUpload:
        receipt = stored.receipt
        call_id = receipt.call_id
        event = self._audio_event(stored)
        if call_id is None:
            ingestion = self.reviews.ingest(
                event,
                preferred_call_id=upload_identifier("call", receipt.upload_id),
            )
            call_id = ingestion.call_id
            self.receipts.attach_call(receipt.upload_id, call_id)
        attempt_id = upload_identifier(f"attempt-{receipt.attempt_number}", receipt.upload_id)
        provenance = self._audio_provenance(stored, event, attempt_id)
        attempt = self.reviews.start_attempt(call_id, provenance)
        self.reviews.advance(call_id, attempt.attempt_id, ProcessingState.VALIDATED)
        self.reviews.advance(call_id, attempt.attempt_id, ProcessingState.QUEUED)
        self.reviews.advance(call_id, attempt.attempt_id, ProcessingState.MEDIA_READY)
        self.reviews.advance(call_id, attempt.attempt_id, ProcessingState.TRANSCRIBING)

        if self._transcription_failure(outcome, attempt.attempt_number):
            retryable = outcome is DeterministicOutcome.TRANSCRIPTION_RETRYABLE_ONCE
            self.reviews.fail(
                call_id,
                attempt.attempt_id,
                SanitizedProcessingFailure(
                    failure_class=FailureClass.TRANSCRIBER_UNAVAILABLE,
                    terminal_state=ProcessingState.TRANSCRIPTION_FAILED,
                    diagnostic_code=(
                        "deterministic_transcription_retryable"
                        if retryable
                        else "deterministic_transcription_terminal"
                    ),
                    retryable=retryable,
                ),
            )
            return self._finish_failure(
                stored,
                state=UploadState.TRANSCRIPTION_FAILED,
                diagnostic_code=(
                    "deterministic_transcription_retryable"
                    if retryable
                    else "deterministic_transcription_terminal"
                ),
                retryable=retryable,
            )

        transcript_payload = self.reviews.transcript_payload(call_id)
        if transcript_payload is None:
            transcript = self.transcriber.transcribe(
                event.call,
                fixture_id=fixture_id,
                call_id=call_id,
                attempt_number=attempt.attempt_number,
                provenance=provenance,
            ).model_copy(
                update={
                    "transcript_id": upload_identifier("transcript", receipt.upload_id),
                    "media_hash_reference": receipt.content_hash_reference,
                    "provider_response_version": "manual-upload-fixture-v1",
                }
            )
            self.reviews.store_transcript(transcript, attempt.attempt_id)
        else:
            transcript = Transcript.model_validate_json(
                json.dumps(transcript_payload, ensure_ascii=False)
            ).model_copy(update={"provenance": provenance})
        self.reviews.advance(call_id, attempt.attempt_id, ProcessingState.TRANSCRIBED)
        self.reviews.advance(call_id, attempt.attempt_id, ProcessingState.EXTRACTING_FACTS)
        facts = self.analyzer.extract_facts(fixture_id, transcript)
        self.reviews.advance(call_id, attempt.attempt_id, ProcessingState.APPLYING_PLAYBOOK)

        if self._analysis_failure(outcome, attempt.attempt_number):
            retryable = outcome is DeterministicOutcome.ANALYSIS_RETRYABLE_ONCE
            self.reviews.fail(
                call_id,
                attempt.attempt_id,
                SanitizedProcessingFailure(
                    failure_class=FailureClass.ANALYZER_UNAVAILABLE,
                    terminal_state=ProcessingState.ANALYSIS_FAILED,
                    diagnostic_code=(
                        "deterministic_analysis_retryable"
                        if retryable
                        else "deterministic_analysis_terminal"
                    ),
                    retryable=retryable,
                ),
            )
            return self._finish_failure(
                stored,
                state=UploadState.ANALYSIS_FAILED,
                diagnostic_code=(
                    "deterministic_analysis_retryable"
                    if retryable
                    else "deterministic_analysis_terminal"
                ),
                retryable=retryable,
            )

        analysis = self.analyzer.apply_playbook(
            fixture_id,
            call_id=call_id,
            facts=facts,
            transcript=transcript,
            provenance=provenance,
        ).model_copy(update={"analysis_id": upload_identifier("analysis", receipt.upload_id)})
        validate_analysis(
            analysis,
            transcript,
            event.call.duration_seconds,
            caller_identity_metadata_verified=False,
        )
        self.reviews.store_analysis(analysis, attempt.attempt_id)
        self.reviews.advance(call_id, attempt.attempt_id, ProcessingState.ANALYZED)
        self._generate_report(receipt.captured_at)
        return self._finish_success(stored)

    def _process_transcript(
        self, stored: StoredUpload, artifact: TranscriptOnlyArtifact
    ) -> StoredUpload:
        outcome = TranscriptOnlyImporter(self.reviews).process(artifact)
        self.receipts.attach_call(stored.receipt.upload_id, outcome.call_id)
        if outcome.terminal_state is not ProcessingState.ANALYZED:
            return self.receipts.complete(
                stored.receipt.upload_id,
                state=UploadState.ANALYSIS_FAILED,
                diagnostic_code="transcript_analysis_failed",
                retryable=False,
                deletion_confirmed=True,
                deleted_at=datetime.now(UTC),
            )
        self._generate_report(stored.receipt.captured_at)
        return self.receipts.complete(
            stored.receipt.upload_id,
            state=UploadState.ANALYZED,
            deletion_confirmed=True,
            deleted_at=datetime.now(UTC),
        )

    def _finish_success(self, stored: StoredUpload) -> StoredUpload:
        deletion = self.store.delete(self._reference(stored))
        if not deletion.deletion_confirmed:
            return self.receipts.complete(
                stored.receipt.upload_id,
                state=UploadState.DELETION_FAILED,
                diagnostic_code="temporary_media_deletion_failed",
                retryable=False,
                deletion_confirmed=False,
            )
        return self.receipts.complete(
            stored.receipt.upload_id,
            state=UploadState.ANALYZED,
            deletion_confirmed=True,
            deleted_at=deletion.occurred_at,
        )

    def _finish_failure(
        self,
        stored: StoredUpload,
        *,
        state: UploadState,
        diagnostic_code: str,
        retryable: bool,
    ) -> StoredUpload:
        if retryable:
            return self.receipts.complete(
                stored.receipt.upload_id,
                state=state,
                diagnostic_code=diagnostic_code,
                retryable=True,
            )
        deletion = self.store.delete(self._reference(stored))
        if not deletion.deletion_confirmed:
            return self.receipts.complete(
                stored.receipt.upload_id,
                state=UploadState.DELETION_FAILED,
                diagnostic_code="temporary_media_deletion_failed",
                retryable=False,
                deletion_confirmed=False,
            )
        return self.receipts.complete(
            stored.receipt.upload_id,
            state=state,
            diagnostic_code=diagnostic_code,
            retryable=False,
            deletion_confirmed=True,
            deleted_at=deletion.occurred_at,
        )

    def _unexpected_audio_failure(self, stored: StoredUpload) -> StoredUpload:
        deletion_confirmed: bool | None = None
        deleted_at: datetime | None = None
        if stored.object_id is not None and stored.artifact_id is not None:
            deletion = self.store.delete(self._reference(stored))
            deletion_confirmed = deletion.deletion_confirmed
            deleted_at = deletion.occurred_at if deletion.deletion_confirmed else None
        return self.receipts.complete(
            stored.receipt.upload_id,
            state=(
                UploadState.ANALYSIS_FAILED
                if deletion_confirmed is not False
                else UploadState.DELETION_FAILED
            ),
            diagnostic_code=(
                "unexpected_processing_failure"
                if deletion_confirmed is not False
                else "temporary_media_deletion_failed"
            ),
            retryable=False,
            deletion_confirmed=deletion_confirmed,
            deleted_at=deleted_at,
        )

    def _record_unexpected_failure(self, error_code: str) -> None:
        if self.operational_logger is None:
            return
        self.operational_logger.event(
            "manual_upload_processing_failed",
            level="error",
            component="manual_upload",
            correlation_id=self.correlation_id or "correlation-unavailable",
            error_code=error_code,
            status="failed",
        )

    def _audio_event(self, stored: StoredUpload) -> IngestionEvent:
        receipt = stored.receipt
        call = NormalizedCall(
            source=CallSource.MANUAL_UPLOAD,
            source_event_id=receipt.source_event_id,
            source_call_id=f"manual-content-{stored.content_fingerprint[:24]}",
            recording_id=stored.artifact_id,
            occurred_at=receipt.captured_at,
            direction=receipt.direction,
            duration_seconds=receipt.validation.duration_seconds,
            staff_extension=receipt.staff_extension,
            language_hint=receipt.language_hint,
            media_reference=stored.object_id,
            transcript_fixture_reference=None,
            metadata={"source_mode": "manual_upload", "synthetic": True},
            synthetic=True,
        )
        return IngestionEvent(
            fixture_id=f"UPL-{receipt.upload_id[:12]}",
            received_at=receipt.created_at,
            call=call,
        )

    def _audio_provenance(
        self, stored: StoredUpload, event: IngestionEvent, attempt_id: str
    ) -> Provenance:
        return Provenance(
            schema_version=cast(Any, SCHEMA_VERSION),
            call_source=CallSource.MANUAL_UPLOAD,
            source_event_id=event.call.source_event_id,
            source_call_id=event.call.source_call_id,
            transcript_adapter="manual-upload-fixture-transcriber",
            transcript_model_version=MANUAL_AUDIO_MODEL,
            analysis_adapter=self.analyzer.adapter_name,
            analysis_model_version=self.analyzer.model_version,
            prompt_version=self.analyzer.prompt_version,
            playbook_version="synthetic-draft-v1",
            adapter_version="manual-upload-local-v1",
            generated_at=datetime.now(UTC),
            processing_attempt_id=attempt_id,
            environment="local_dev",
            transcription_transport=TranscriptionTransportProvenance(
                transport="fixture",
                declared_contract_version=MANUAL_AUDIO_CONTRACT,
                observed_cli_version="unavailable",
                model_id=MANUAL_AUDIO_MODEL,
                requested_response_format="fixture-json",
                generated_asset_fingerprint=stored.receipt.content_hash_reference,
                attempt_number=stored.receipt.attempt_number,
                result_kind="deterministic_fixture",
            ),
        )

    def _reference(self, stored: StoredUpload) -> TemporaryObjectReference:
        if stored.object_id is None or stored.artifact_id is None:
            raise ValueError("temporary_media_unavailable")
        return TemporaryObjectReference(
            object_id=stored.object_id,
            artifact_id=stored.artifact_id,
            store_name="local-synthetic-v1",
            synthetic=True,
            created_at=stored.receipt.created_at,
        )

    def _generate_report(self, captured_at: datetime) -> None:
        timezone = ZoneInfo(self.settings.firm_timezone)
        business_date = captured_at.astimezone(timezone).date()
        cutoff = datetime.combine(business_date, time(18, 0), tzinfo=timezone)
        expected = self.experience.expected_source_call_ids(business_date)
        self.experience.generate_report(
            business_date=business_date,
            cutoff_at=cutoff,
            expected_source_call_ids=expected,
        )

    @staticmethod
    def _validate_timestamp(metadata: UploadMetadata) -> None:
        now = datetime.now(UTC)
        captured = metadata.captured_at.astimezone(UTC)
        if captured > now + timedelta(minutes=5) or captured < now - timedelta(days=366):
            raise UploadRequestError("captured_at_outside_boundary")

    @staticmethod
    def _validate_declared_media(
        parsed: ParsedAudioUpload,
        detected_format: SupportedMediaFormat,
        detected_content_type: MediaContentType,
    ) -> None:
        extensions = {
            SupportedMediaFormat.WAV: {"wav"},
            SupportedMediaFormat.MP3: {"mp3"},
            SupportedMediaFormat.MPEG: {"mpeg", "mpga", "mp3"},
            SupportedMediaFormat.MPGA: {"mpga", "mpeg", "mp3"},
            SupportedMediaFormat.M4A: {"m4a", "mp4"},
            SupportedMediaFormat.MP4: {"m4a", "mp4"},
            SupportedMediaFormat.WEBM: {"webm"},
        }
        content_types = {
            MediaContentType.AUDIO_WAV: {"audio/wav", "audio/x-wav"},
            MediaContentType.AUDIO_MPEG: {"audio/mpeg"},
            MediaContentType.AUDIO_MP4: {"audio/mp4", "audio/x-m4a", "video/mp4"},
            MediaContentType.VIDEO_MP4: {"video/mp4", "audio/mp4"},
            MediaContentType.AUDIO_WEBM: {"audio/webm", "video/webm"},
        }
        if (
            parsed.filename_extension not in extensions[detected_format]
            or parsed.declared_content_type not in content_types[detected_content_type]
        ):
            raise UploadRequestError("detected_media_mismatch")

    @staticmethod
    def _transcription_failure(outcome: DeterministicOutcome, attempt_number: int) -> bool:
        return outcome is DeterministicOutcome.TRANSCRIPTION_TERMINAL or (
            outcome is DeterministicOutcome.TRANSCRIPTION_RETRYABLE_ONCE and attempt_number == 1
        )

    @staticmethod
    def _analysis_failure(outcome: DeterministicOutcome, attempt_number: int) -> bool:
        return outcome is DeterministicOutcome.ANALYSIS_TERMINAL or (
            outcome is DeterministicOutcome.ANALYSIS_RETRYABLE_ONCE and attempt_number == 1
        )

    def _delete_references(
        self,
        source: TemporaryObjectReference | None,
        retained: TemporaryObjectReference | None,
    ) -> None:
        seen: set[str] = set()
        for reference in (source, retained):
            if reference is not None and reference.object_id not in seen:
                seen.add(reference.object_id)
                self.store.delete(reference)
