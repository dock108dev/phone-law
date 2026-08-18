"""Transactional, content-free persistence for local synthetic upload receipts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import uuid4
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from pydantic import BaseModel
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError

from packages.contracts.manual_upload import (
    UploadKind,
    UploadMetadata,
    UploadReceipt,
    UploadState,
    UploadStateEvent,
    UploadValidationSummary,
)
from packages.contracts.report import DemoPrincipal, DemoPrincipalId, DemoRole
from packages.contracts.review import Direction
from packages.database.review_schema import manual_upload_receipts, manual_upload_state_events

MANUAL_UPLOAD_ADAPTER_VERSION = "manual-upload-local-v1"
FIRM_TIMEZONE = ZoneInfo("America/New_York")


def upload_identifier(kind: str, value: str) -> str:
    return hashlib.sha256(f"manual-upload-{kind}:{value}".encode()).hexdigest()[:32]


def source_event_identifier(upload_id: str) -> str:
    return f"upload-event-{upload_id}"


@dataclass(frozen=True)
class StoredUpload:
    receipt: UploadReceipt
    client_submission_id: str
    content_fingerprint: str
    object_id: str | None
    artifact_id: str | None


@dataclass(frozen=True)
class CreateReceiptResult:
    stored: StoredUpload
    duplicate: bool


class SubmissionConflictError(ValueError):
    """A client submission identifier was reused for different content."""


class UploadStateConflictError(ValueError):
    """The requested lifecycle operation is not available in the current state."""


def _validated[ModelT: BaseModel](model: type[ModelT], payload: object) -> ModelT:
    return model.model_validate_json(json.dumps(payload, ensure_ascii=False))


class ManualUploadRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def create(
        self,
        *,
        metadata: UploadMetadata,
        kind: UploadKind,
        content_fingerprint: str,
        validation: UploadValidationSummary,
        principal: DemoPrincipal,
        object_id: str | None,
        artifact_id: str | None,
    ) -> CreateReceiptResult:
        existing_submission = self.by_submission(metadata.client_submission_id)
        if existing_submission is not None:
            if existing_submission.content_fingerprint != content_fingerprint:
                raise SubmissionConflictError("submission_content_conflict")
            return CreateReceiptResult(stored=existing_submission, duplicate=True)
        existing_content = self.by_content(content_fingerprint)
        if existing_content is not None:
            return CreateReceiptResult(stored=existing_content, duplicate=True)

        upload_id = uuid4().hex
        now = datetime.now(UTC)
        values = {
            "id": upload_id,
            "client_submission_id": metadata.client_submission_id,
            "source_event_id": source_event_identifier(upload_id),
            "call_id": None,
            "submission_kind": kind.value,
            "is_synthetic": True,
            "content_fingerprint": content_fingerprint,
            "language_hint": metadata.language_hint,
            "direction": metadata.direction.value,
            "captured_at": metadata.captured_at,
            "staff_extension": metadata.staff_extension,
            "principal_id": principal.principal_id.value,
            "role": principal.role.value,
            "state": UploadState.READY.value,
            "attempt_number": 0,
            "diagnostic_code": None,
            "retryable": False,
            "object_id": object_id,
            "artifact_id": artifact_id,
            "validation_summary": validation.model_dump(mode="json"),
            "deletion_confirmed": None,
            "adapter_version": MANUAL_UPLOAD_ADAPTER_VERSION,
            "created_at": now,
            "updated_at": now + timedelta(microseconds=2),
            "cancelled_at": None,
            "deleted_at": None,
        }
        try:
            with self.engine.begin() as connection:
                connection.execute(manual_upload_receipts.insert().values(**values))
                for offset, state in enumerate(
                    (UploadState.RECEIVED, UploadState.VALIDATING, UploadState.READY)
                ):
                    self._insert_event(
                        connection,
                        upload_id=upload_id,
                        state=state,
                        attempt_number=0,
                        diagnostic_code=None,
                        occurred_at=now + timedelta(microseconds=offset),
                    )
        except IntegrityError:
            raced_submission = self.by_submission(metadata.client_submission_id)
            if raced_submission is not None:
                if raced_submission.content_fingerprint != content_fingerprint:
                    raise SubmissionConflictError("submission_content_conflict") from None
                return CreateReceiptResult(stored=raced_submission, duplicate=True)
            raced_content = self.by_content(content_fingerprint)
            if raced_content is not None:
                return CreateReceiptResult(stored=raced_content, duplicate=True)
            raise
        stored = self.get(upload_id)
        if stored is None:
            raise RuntimeError("manual_upload_receipt_unavailable")
        return CreateReceiptResult(stored=stored, duplicate=False)

    @staticmethod
    def _insert_event(
        connection: sa.Connection,
        *,
        upload_id: str,
        state: UploadState,
        attempt_number: int,
        diagnostic_code: str | None,
        occurred_at: datetime,
    ) -> None:
        connection.execute(
            manual_upload_state_events.insert().values(
                id=uuid4().hex,
                upload_id=upload_id,
                state=state.value,
                attempt_number=attempt_number,
                diagnostic_code=diagnostic_code,
                occurred_at=occurred_at,
            )
        )

    def by_submission(self, client_submission_id: str) -> StoredUpload | None:
        return self._one(manual_upload_receipts.c.client_submission_id == client_submission_id)

    def by_content(self, content_fingerprint: str) -> StoredUpload | None:
        return self._one(manual_upload_receipts.c.content_fingerprint == content_fingerprint)

    def get(self, upload_id: str) -> StoredUpload | None:
        return self._one(manual_upload_receipts.c.id == upload_id)

    def _one(self, condition: sa.ColumnElement[bool]) -> StoredUpload | None:
        with self.engine.connect() as connection:
            row = (
                connection.execute(sa.select(manual_upload_receipts).where(condition))
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            history = self._history(connection, str(row["id"]))
        return self._stored(row, history)

    def list(self) -> tuple[StoredUpload, ...]:
        with self.engine.connect() as connection:
            rows = (
                connection.execute(
                    sa.select(manual_upload_receipts).order_by(
                        manual_upload_receipts.c.created_at.desc(),
                        manual_upload_receipts.c.id,
                    )
                )
                .mappings()
                .all()
            )
            return tuple(
                self._stored(row, self._history(connection, str(row["id"]))) for row in rows
            )

    @staticmethod
    def _history(connection: sa.Connection, upload_id: str) -> tuple[UploadStateEvent, ...]:
        rows = (
            connection.execute(
                sa.select(manual_upload_state_events)
                .where(manual_upload_state_events.c.upload_id == upload_id)
                .order_by(
                    manual_upload_state_events.c.occurred_at,
                    manual_upload_state_events.c.id,
                )
            )
            .mappings()
            .all()
        )
        return tuple(
            UploadStateEvent(
                event_id=str(row["id"]),
                state=UploadState(str(row["state"])),
                attempt_number=int(row["attempt_number"]),
                diagnostic_code=cast(str | None, row["diagnostic_code"]),
                occurred_at=cast(datetime, row["occurred_at"]),
            )
            for row in rows
        )

    @staticmethod
    def _stored(row: sa.RowMapping, history: tuple[UploadStateEvent, ...]) -> StoredUpload:
        call_id = cast(str | None, row["call_id"])
        captured_at = cast(datetime, row["captured_at"])
        receipt = UploadReceipt(
            upload_id=str(row["id"]),
            source_event_id=str(row["source_event_id"]),
            call_id=call_id,
            submission_kind=UploadKind(str(row["submission_kind"])),
            content_hash_reference=f"sha256:{str(row['content_fingerprint'])[:12]}",
            language_hint=cast(Any, row["language_hint"]),
            direction=Direction(str(row["direction"])),
            captured_at=captured_at,
            staff_extension=cast(str, row["staff_extension"]),
            principal_id=DemoPrincipalId(str(row["principal_id"])),
            role=DemoRole(str(row["role"])),
            state=UploadState(str(row["state"])),
            attempt_number=int(row["attempt_number"]),
            diagnostic_code=cast(str | None, row["diagnostic_code"]),
            retryable=bool(row["retryable"]),
            deletion_confirmed=cast(bool | None, row["deletion_confirmed"]),
            validation=_validated(UploadValidationSummary, row["validation_summary"]),
            created_at=cast(datetime, row["created_at"]),
            updated_at=cast(datetime, row["updated_at"]),
            cancelled_at=cast(datetime | None, row["cancelled_at"]),
            deleted_at=cast(datetime | None, row["deleted_at"]),
            call_path=f"/calls/{call_id}" if call_id else None,
            report_path=(
                f"/reports/{captured_at.astimezone(FIRM_TIMEZONE).date().isoformat()}"
                if call_id
                else None
            ),
            history=history,
        )
        return StoredUpload(
            receipt=receipt,
            client_submission_id=str(row["client_submission_id"]),
            content_fingerprint=str(row["content_fingerprint"]),
            object_id=cast(str | None, row["object_id"]),
            artifact_id=cast(str | None, row["artifact_id"]),
        )

    def claim_processing(self, upload_id: str) -> StoredUpload:
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(manual_upload_receipts)
                    .where(manual_upload_receipts.c.id == upload_id)
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise LookupError("upload_receipt_not_found")
            state = UploadState(str(row["state"]))
            retryable = bool(row["retryable"])
            if state is UploadState.ANALYZED:
                return self._stored(row, self._history(connection, upload_id))
            if state is not UploadState.READY and not (
                retryable
                and state in {UploadState.TRANSCRIPTION_FAILED, UploadState.ANALYSIS_FAILED}
            ):
                raise UploadStateConflictError("upload_not_processable")
            attempt_number = int(row["attempt_number"]) + 1
            now = datetime.now(UTC)
            connection.execute(
                manual_upload_receipts.update()
                .where(manual_upload_receipts.c.id == upload_id)
                .values(
                    state=UploadState.PROCESSING.value,
                    attempt_number=attempt_number,
                    diagnostic_code=None,
                    retryable=False,
                    updated_at=now,
                )
            )
            self._insert_event(
                connection,
                upload_id=upload_id,
                state=UploadState.PROCESSING,
                attempt_number=attempt_number,
                diagnostic_code=None,
                occurred_at=now,
            )
        stored = self.get(upload_id)
        if stored is None:
            raise RuntimeError("manual_upload_receipt_unavailable")
        return stored

    def attach_call(self, upload_id: str, call_id: str) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                manual_upload_receipts.update()
                .where(
                    manual_upload_receipts.c.id == upload_id,
                    manual_upload_receipts.c.call_id.is_(None),
                )
                .values(call_id=call_id, updated_at=datetime.now(UTC))
            )

    def complete(
        self,
        upload_id: str,
        *,
        state: UploadState,
        diagnostic_code: str | None = None,
        retryable: bool = False,
        deletion_confirmed: bool | None = None,
        deleted_at: datetime | None = None,
    ) -> StoredUpload:
        if state not in {
            UploadState.ANALYZED,
            UploadState.TRANSCRIPTION_FAILED,
            UploadState.ANALYSIS_FAILED,
            UploadState.DELETION_FAILED,
        }:
            raise ValueError("unsupported upload completion state")
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            row = connection.execute(
                sa.select(
                    manual_upload_receipts.c.state,
                    manual_upload_receipts.c.attempt_number,
                )
                .where(manual_upload_receipts.c.id == upload_id)
                .with_for_update()
            ).one_or_none()
            if row is None:
                raise LookupError("upload_receipt_not_found")
            if UploadState(str(row.state)) is not UploadState.PROCESSING:
                raise UploadStateConflictError("upload_not_processing")
            connection.execute(
                manual_upload_receipts.update()
                .where(manual_upload_receipts.c.id == upload_id)
                .values(
                    state=state.value,
                    diagnostic_code=diagnostic_code,
                    retryable=retryable,
                    deletion_confirmed=deletion_confirmed,
                    deleted_at=deleted_at,
                    object_id=None if deletion_confirmed else manual_upload_receipts.c.object_id,
                    updated_at=now,
                )
            )
            self._insert_event(
                connection,
                upload_id=upload_id,
                state=state,
                attempt_number=int(row.attempt_number),
                diagnostic_code=diagnostic_code,
                occurred_at=now,
            )
        stored = self.get(upload_id)
        if stored is None:
            raise RuntimeError("manual_upload_receipt_unavailable")
        return stored

    def cancel(self, upload_id: str) -> tuple[StoredUpload, bool]:
        now = datetime.now(UTC)
        changed = False
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(manual_upload_receipts)
                    .where(manual_upload_receipts.c.id == upload_id)
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise LookupError("upload_receipt_not_found")
            state = UploadState(str(row["state"]))
            if state is UploadState.CANCELLED:
                return self._stored(row, self._history(connection, upload_id)), False
            if state is not UploadState.READY:
                raise UploadStateConflictError("processing_already_started")
            changed = True
            connection.execute(
                manual_upload_receipts.update()
                .where(manual_upload_receipts.c.id == upload_id)
                .values(
                    state=UploadState.CANCELLED.value,
                    cancelled_at=now,
                    updated_at=now,
                )
            )
            self._insert_event(
                connection,
                upload_id=upload_id,
                state=UploadState.CANCELLED,
                attempt_number=0,
                diagnostic_code=None,
                occurred_at=now,
            )
        stored = self.get(upload_id)
        if stored is None:
            raise RuntimeError("manual_upload_receipt_unavailable")
        return stored, changed

    def confirm_cancel_deletion(self, upload_id: str, *, confirmed: bool) -> StoredUpload:
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            row = connection.execute(
                sa.select(manual_upload_receipts.c.attempt_number)
                .where(manual_upload_receipts.c.id == upload_id)
                .with_for_update()
            ).one()
            values: dict[str, object] = {
                "deletion_confirmed": confirmed,
                "deleted_at": now if confirmed else None,
                "object_id": None if confirmed else manual_upload_receipts.c.object_id,
                "updated_at": now,
            }
            if not confirmed:
                values.update(
                    state=UploadState.DELETION_FAILED.value,
                    diagnostic_code="temporary_media_deletion_failed",
                    retryable=False,
                )
            connection.execute(
                manual_upload_receipts.update()
                .where(manual_upload_receipts.c.id == upload_id)
                .values(**values)
            )
            if not confirmed:
                self._insert_event(
                    connection,
                    upload_id=upload_id,
                    state=UploadState.DELETION_FAILED,
                    attempt_number=int(row.attempt_number),
                    diagnostic_code="temporary_media_deletion_failed",
                    occurred_at=now,
                )
        stored = self.get(upload_id)
        if stored is None:
            raise RuntimeError("manual_upload_receipt_unavailable")
        return stored
