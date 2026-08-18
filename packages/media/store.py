"""Restrictive temporary object store for generated synthetic media only."""

from __future__ import annotations

import os
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from packages.config import AppProfile
from packages.contracts.media import (
    MediaDeletionEvent,
    MediaErrorClass,
    MediaLifecycleState,
    TemporaryObjectReference,
)

OBJECT_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")


class SyntheticObjectStoreError(ValueError):
    """Safe object-store boundary failure without a caller-supplied path."""


class LocalSyntheticObjectStore:
    store_name = "local-synthetic-v1"

    def __init__(
        self,
        root: Path,
        *,
        profile: AppProfile,
        approved_source_root: Path | None = None,
    ) -> None:
        if profile not in {AppProfile.TEST, AppProfile.DEMO, AppProfile.LIVE_TEST}:
            raise SyntheticObjectStoreError("local_synthetic_store_profile_forbidden")
        self.root = self._validate_root(root)
        self.approved_source_root = (
            self._validate_root(approved_source_root, create=False)
            if approved_source_root is not None
            else None
        )
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)

    @staticmethod
    def _validate_root(root: Path, *, create: bool = True) -> Path:
        if not root.is_absolute():
            raise SyntheticObjectStoreError("temporary_root_must_be_absolute")
        if root.exists() and root.is_symlink():
            raise SyntheticObjectStoreError("temporary_root_symlink_forbidden")
        resolved = root.resolve(strict=False)
        if not str(resolved).startswith("/tmp/colacci-law-"):  # nosec B108
            raise SyntheticObjectStoreError("temporary_root_outside_boundary")
        if not create and not resolved.is_dir():
            raise SyntheticObjectStoreError("approved_source_root_unavailable")
        return resolved

    def _safe_path(self, object_id: str) -> Path:
        if not OBJECT_ID_PATTERN.fullmatch(object_id):
            raise SyntheticObjectStoreError("invalid_object_identifier")
        candidate = self.root / object_id
        if candidate.parent.resolve(strict=True) != self.root:
            raise SyntheticObjectStoreError("object_path_outside_boundary")
        if candidate.is_symlink():
            raise SyntheticObjectStoreError("object_symlink_forbidden")
        return candidate

    def _assert_approved_source(self, source: Path) -> Path:
        if source.is_symlink() or not source.is_file():
            raise SyntheticObjectStoreError("source_file_invalid")
        resolved = source.resolve(strict=True)
        if self.approved_source_root is None:
            raise SyntheticObjectStoreError("approved_source_root_required")
        try:
            resolved.relative_to(self.approved_source_root)
        except ValueError as exc:
            raise SyntheticObjectStoreError("source_outside_approved_root") from exc
        return resolved

    def import_file(self, source: Path, *, artifact_id: str) -> TemporaryObjectReference:
        approved = self._assert_approved_source(source)
        reference, destination = self.allocate(artifact_id=artifact_id)
        shutil.copyfile(approved, destination)
        os.chmod(destination, 0o600)
        return reference

    def allocate(self, *, artifact_id: str) -> tuple[TemporaryObjectReference, Path]:
        object_id = uuid4().hex
        destination = self._safe_path(object_id)
        descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        return (
            TemporaryObjectReference(
                object_id=object_id,
                artifact_id=artifact_id,
                store_name="local-synthetic-v1",
                synthetic=True,
                created_at=datetime.now(UTC),
            ),
            destination,
        )

    def resolve(self, reference: TemporaryObjectReference) -> Path:
        if reference.store_name != self.store_name or not reference.synthetic:
            raise SyntheticObjectStoreError("object_reference_store_mismatch")
        path = self._safe_path(reference.object_id)
        if not path.is_file():
            raise SyntheticObjectStoreError("object_unavailable")
        return path

    def permission_mode(self, reference: TemporaryObjectReference) -> int:
        return self.resolve(reference).stat().st_mode & 0o777

    def exists(self, reference: TemporaryObjectReference) -> bool:
        try:
            return self._safe_path(reference.object_id).is_file()
        except SyntheticObjectStoreError:
            return False

    def delete(self, reference: TemporaryObjectReference) -> MediaDeletionEvent:
        path = self._safe_path(reference.object_id)
        try:
            path.unlink(missing_ok=True)
            confirmed = not path.exists()
        except OSError:
            confirmed = False
        return MediaDeletionEvent(
            event_id=uuid4().hex,
            artifact_id=reference.artifact_id,
            object_id=reference.object_id,
            state=MediaLifecycleState.DELETED,
            deletion_confirmed=confirmed,
            error_class=None if confirmed else MediaErrorClass.MEDIA_DELETION_FAILED,
            occurred_at=datetime.now(UTC),
        )
