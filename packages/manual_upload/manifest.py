"""Private generated-audio fingerprint allowlist for deterministic local processing."""

from __future__ import annotations

import stat
from pathlib import Path

from packages.contracts.manual_upload import SyntheticManifestEntry, SyntheticUploadManifest

MAX_MANIFEST_BYTES = 64 * 1024


class SyntheticManifestError(ValueError):
    """Safe manifest-boundary failure."""


class SyntheticFingerprintManifest:
    def __init__(self, path: Path) -> None:
        if not path.is_absolute() or not str(path.resolve(strict=False)).startswith(
            "/tmp/colacci-law-slice4-"  # nosec B108
        ):
            raise SyntheticManifestError("synthetic_manifest_outside_boundary")
        try:
            info = path.lstat()
        except OSError as exc:
            raise SyntheticManifestError("synthetic_manifest_unavailable") from exc
        if path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
            raise SyntheticManifestError("synthetic_manifest_permissions_invalid")
        if info.st_size <= 0 or info.st_size > MAX_MANIFEST_BYTES:
            raise SyntheticManifestError("synthetic_manifest_size_invalid")
        try:
            manifest = SyntheticUploadManifest.model_validate_json(path.read_bytes())
        except (OSError, ValueError) as exc:
            raise SyntheticManifestError("synthetic_manifest_invalid") from exc
        self._entries = {entry.content_sha256: entry for entry in manifest.entries}

    def entry(self, content_sha256: str) -> SyntheticManifestEntry:
        try:
            return self._entries[content_sha256]
        except KeyError as exc:
            raise SyntheticManifestError("synthetic_fingerprint_not_allowlisted") from exc
