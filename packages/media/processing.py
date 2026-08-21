"""Content-based media inspection and channel-preserving normalization."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess  # nosec B404
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from packages.contracts.media import (
    MediaContentType,
    MediaErrorClass,
    MediaInspectionResult,
    NormalizationResult,
    SupportedMediaFormat,
    TemporaryObjectReference,
)
from packages.media.store import LocalSyntheticObjectStore


class MediaBoundaryError(RuntimeError):
    def __init__(self, error_class: MediaErrorClass) -> None:
        super().__init__(error_class.value)
        self.error_class = error_class


class MediaInspector:
    def __init__(
        self,
        *,
        max_bytes: int,
        max_duration_seconds: float,
        allowed_root: Path,
        ffprobe_binary: Path = Path("/usr/bin/ffprobe"),
    ) -> None:
        if max_bytes <= 0 or max_bytes > 25 * 1024 * 1024:
            raise ValueError("media byte cap must be between 1 and 25 MB")
        if max_duration_seconds <= 0:
            raise ValueError("media duration cap must be positive")
        self.max_bytes = max_bytes
        self.max_duration_seconds = max_duration_seconds
        self.allowed_root = allowed_root.resolve(strict=True)
        self.ffprobe_binary = ffprobe_binary

    def _safe_media_path(self, path: Path) -> Path:
        if path.is_symlink() or not path.is_file():
            raise MediaBoundaryError(MediaErrorClass.CORRUPT_MEDIA)
        resolved = path.resolve(strict=True)
        try:
            resolved.relative_to(self.allowed_root)
        except ValueError as exc:
            raise MediaBoundaryError(MediaErrorClass.CORRUPT_MEDIA) from exc
        return resolved

    @staticmethod
    def _has_supported_signature(header: bytes) -> bool:
        return (
            (header.startswith(b"RIFF") and header[8:12] == b"WAVE")
            or header.startswith(b"ID3")
            or (len(header) >= 2 and header[0] == 0xFF and header[1] & 0xE0 == 0xE0)
            or (len(header) >= 8 and header[4:8] == b"ftyp")
            or header.startswith(b"\x1aE\xdf\xa3")
        )

    def inspect(self, path: Path, *, artifact_id: str) -> MediaInspectionResult:
        safe_path = self._safe_media_path(path)
        byte_size = safe_path.stat().st_size
        if byte_size == 0:
            raise MediaBoundaryError(MediaErrorClass.EMPTY_MEDIA)
        if byte_size > self.max_bytes:
            raise MediaBoundaryError(MediaErrorClass.OVERSIZED_MEDIA)

        digest = hashlib.sha256()
        with safe_path.open("rb") as media_file:
            header = media_file.read(16)
            digest.update(header)
            for block in iter(lambda: media_file.read(1024 * 1024), b""):
                digest.update(block)
        if not self._has_supported_signature(header):
            raise MediaBoundaryError(MediaErrorClass.UNSUPPORTED_MEDIA)

        command = [
            str(self.ffprobe_binary),
            "-v",
            "error",
            "-show_entries",
            "format=format_name,duration:stream=codec_type,codec_name,sample_rate,channels",
            "-of",
            "json",
            str(safe_path),
        ]
        try:
            completed = subprocess.run(  # noqa: S603  # nosec B603
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=15,
            )
            payload = cast(dict[str, Any], json.loads(completed.stdout))
            inspection = self._parse_probe(payload)
        except (
            json.JSONDecodeError,
            KeyError,
            OSError,
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
            TypeError,
            ValueError,
        ) as exc:
            raise MediaBoundaryError(MediaErrorClass.CORRUPT_MEDIA) from exc

        if inspection[2] > self.max_duration_seconds:
            raise MediaBoundaryError(MediaErrorClass.OVERLONG_MEDIA)
        return MediaInspectionResult(
            artifact_id=artifact_id,
            synthetic=True,
            media_format=inspection[0],
            content_type=inspection[1],
            byte_size=byte_size,
            duration_seconds=inspection[2],
            sample_rate_hz=inspection[3],
            channel_count=inspection[4],
            codec=inspection[5],
            content_sha256=digest.hexdigest(),
            inspected_at=datetime.now(UTC),
        )

    @staticmethod
    def _parse_probe(
        payload: dict[str, Any],
    ) -> tuple[SupportedMediaFormat, MediaContentType, float, int, int, str]:
        format_payload = cast(dict[str, Any], payload["format"])
        format_names = set(str(format_payload["format_name"]).split(","))
        media_format, content_type = _map_format(format_names)
        duration = float(format_payload["duration"])
        streams = cast(list[dict[str, Any]], payload["streams"])
        stream = next(item for item in streams if item.get("codec_type") == "audio")
        sample_rate = int(stream["sample_rate"])
        channels = int(stream["channels"])
        codec = str(stream["codec_name"])
        if duration <= 0 or sample_rate <= 0 or channels <= 0 or not codec:
            raise ValueError("invalid media metadata")
        return media_format, content_type, duration, sample_rate, channels, codec


def _map_format(
    names: set[str],
) -> tuple[SupportedMediaFormat, MediaContentType]:
    if "wav" in names:
        return SupportedMediaFormat.WAV, MediaContentType.AUDIO_WAV
    if "mp3" in names:
        return SupportedMediaFormat.MP3, MediaContentType.AUDIO_MPEG
    if "webm" in names or "matroska" in names:
        return SupportedMediaFormat.WEBM, MediaContentType.AUDIO_WEBM
    if "mov" in names or "mp4" in names or "m4a" in names:
        return SupportedMediaFormat.M4A, MediaContentType.AUDIO_MP4
    if "mpeg" in names:
        return SupportedMediaFormat.MPEG, MediaContentType.AUDIO_MPEG
    raise ValueError("unsupported probed format")


class MediaNormalizer:
    def __init__(
        self,
        *,
        store: LocalSyntheticObjectStore,
        inspector: MediaInspector,
        ffmpeg_binary: Path = Path("/usr/bin/ffmpeg"),
    ) -> None:
        self.store = store
        self.inspector = inspector
        self.ffmpeg_binary = ffmpeg_binary

    def normalize(
        self,
        source: TemporaryObjectReference,
        inspection: MediaInspectionResult,
    ) -> tuple[TemporaryObjectReference, NormalizationResult]:
        if (
            inspection.media_format is SupportedMediaFormat.WAV
            and inspection.codec == "pcm_s16le"
            and inspection.sample_rate_hz == 16000
        ):
            return source, self._result(source, source, inspection, normalized=False)

        normalized, output_path = self.store.allocate(artifact_id=inspection.artifact_id)
        input_path = self.store.resolve(source)
        command = [
            str(self.ffmpeg_binary),
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-i",
            str(input_path),
            "-vn",
            "-ac",
            str(inspection.channel_count),
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            "-f",
            "wav",
            str(output_path),
        ]
        try:
            subprocess.run(  # noqa: S603  # nosec B603
                command,
                check=True,
                capture_output=True,
                timeout=30,
            )
            os.chmod(output_path, 0o600)
            normalized_inspection = self.inspector.inspect(
                output_path,
                artifact_id=inspection.artifact_id,
            )
        except (MediaBoundaryError, OSError, subprocess.SubprocessError) as exc:
            self.store.delete(normalized)
            raise MediaBoundaryError(MediaErrorClass.NORMALIZATION_FAILED) from exc
        if normalized_inspection.channel_count != inspection.channel_count:
            self.store.delete(normalized)
            raise MediaBoundaryError(MediaErrorClass.NORMALIZATION_FAILED)
        return (
            normalized,
            self._result(source, normalized, normalized_inspection, normalized=True),
        )

    @staticmethod
    def _result(
        source: TemporaryObjectReference,
        normalized_reference: TemporaryObjectReference,
        inspection: MediaInspectionResult,
        *,
        normalized: bool,
    ) -> NormalizationResult:
        return NormalizationResult(
            artifact_id=inspection.artifact_id,
            source_object_id=source.object_id,
            normalized_object_id=normalized_reference.object_id,
            normalized=normalized,
            media_format=inspection.media_format,
            byte_size=inspection.byte_size,
            duration_seconds=inspection.duration_seconds,
            sample_rate_hz=inspection.sample_rate_hz,
            channel_count=inspection.channel_count,
            content_sha256=inspection.content_sha256,
        )
