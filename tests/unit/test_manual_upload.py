from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from packages.contracts.manual_upload import (
    SyntheticManifestEntry,
    SyntheticUploadManifest,
    UploadKind,
    UploadMetadata,
    UploadState,
    UploadValidationSummary,
)
from packages.manual_upload.manifest import SyntheticFingerprintManifest, SyntheticManifestError
from packages.manual_upload.request_boundary import (
    UploadRequestError,
    parse_audio_multipart,
    parse_header_metadata,
    require_bounded_content_length,
)


def multipart(
    filename: str = "generated.wav", payload: bytes = b"RIFF0000WAVE"
) -> tuple[bytes, str]:
    boundary = "slice4-test-boundary"
    fields = {
        "client_submission_id": "browser-0123456789abcdef012345",
        "generated_only_attestation": "true",
        "direction": "inbound",
        "captured_at": "2026-08-18T12:00:00Z",
        "language_hint": "en",
        "staff_extension": "SYN-104",
    }
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
            ).encode()
        )
    parts.append(
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
            f'filename="{filename}"\r\nContent-Type: audio/wav\r\n\r\n'
        ).encode()
        + payload
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def test_bounded_single_audio_request_parses_safe_metadata() -> None:
    body, content_type = multipart()
    parsed = parse_audio_multipart(body, content_type=content_type, max_media_bytes=1024)
    assert parsed.filename_extension == "wav"
    assert parsed.metadata.generated_only_attestation is True
    assert parsed.metadata.staff_extension == "SYN-104"
    assert parsed.payload == b"RIFF0000WAVE"


@pytest.mark.parametrize(
    "filename",
    [".hidden.wav", "../escape.wav", "double.payload.wav", "unsafe\\name.wav", "bad.exe"],
)
def test_unsafe_or_double_extension_filename_is_rejected(filename: str) -> None:
    body, content_type = multipart(filename)
    with pytest.raises(UploadRequestError, match="unsafe_filename"):
        parse_audio_multipart(body, content_type=content_type, max_media_bytes=1024)


def test_request_size_and_attestation_fail_closed() -> None:
    with pytest.raises(UploadRequestError, match="content_length_required"):
        require_bounded_content_length(None, maximum=10)
    with pytest.raises(UploadRequestError, match="upload_body_too_large"):
        require_bounded_content_length("11", maximum=10)
    headers = {
        "x-client-submission-id": "browser-0123456789abcdef012345",
        "x-generated-only-attestation": "false",
        "x-upload-direction": "inbound",
        "x-upload-captured-at": "2026-08-18T12:00:00Z",
        "x-upload-language": "en",
        "x-upload-staff-extension": "SYN-104",
    }
    with pytest.raises(UploadRequestError, match="generated_only_attestation_required"):
        parse_header_metadata(headers)


def test_upload_metadata_rejects_caller_role_and_bad_extension() -> None:
    payload = {
        "client_submission_id": "browser-0123456789abcdef012345",
        "generated_only_attestation": True,
        "direction": "inbound",
        "captured_at": datetime.now(UTC).isoformat(),
        "language_hint": "en",
        "staff_extension": "104",
        "role": "administrator",
    }
    with pytest.raises(ValidationError):
        UploadMetadata.model_validate_json(json.dumps(payload))


def test_validation_summary_requires_kind_specific_shape() -> None:
    audio = UploadValidationSummary(
        kind=UploadKind.SYNTHETIC_AUDIO,
        contract_version="media-contract-v1",
        byte_size=44,
        duration_seconds=1,
        media_format="wav",
        channel_count=1,
        sample_rate_hz=16_000,
    )
    transcript = UploadValidationSummary(
        kind=UploadKind.TRANSCRIPT_ONLY,
        contract_version="transcript-only-artifact-v1",
        byte_size=100,
        duration_seconds=1,
        segment_count=1,
    )
    assert audio.kind is UploadKind.SYNTHETIC_AUDIO
    assert transcript.kind is UploadKind.TRANSCRIPT_ONLY
    with pytest.raises(ValidationError, match="audio validation summary is incomplete"):
        UploadValidationSummary(
            kind=UploadKind.SYNTHETIC_AUDIO,
            contract_version="media-contract-v1",
            byte_size=44,
            duration_seconds=1,
            segment_count=1,
        )
    with pytest.raises(ValidationError, match="transcript validation summary is incomplete"):
        UploadValidationSummary(
            kind=UploadKind.TRANSCRIPT_ONLY,
            contract_version="transcript-only-artifact-v1",
            byte_size=100,
            duration_seconds=1,
            segment_count=1,
            media_format="wav",
        )


def test_synthetic_manifest_requires_unique_nonempty_fingerprints() -> None:
    entry = SyntheticManifestEntry(content_sha256="a" * 64, fixture_id="CL-FX-002")
    with pytest.raises(ValidationError, match="nonempty and unique"):
        SyntheticUploadManifest(
            manifest_version="manual-upload-synthetic-manifest-v1",
            generated_only=True,
            entries=(),
        )
    with pytest.raises(ValidationError, match="nonempty and unique"):
        SyntheticUploadManifest(
            manifest_version="manual-upload-synthetic-manifest-v1",
            generated_only=True,
            entries=(entry, entry),
        )


def test_private_manifest_loads_and_rejects_unknown_fingerprint() -> None:
    with tempfile.TemporaryDirectory(prefix="colacci-law-slice4-unit-", dir="/tmp") as directory:
        path = Path(directory) / "manifest.json"
        path.write_text(
            json.dumps(
                {
                    "manifest_version": "manual-upload-synthetic-manifest-v1",
                    "generated_only": True,
                    "entries": [
                        {
                            "content_sha256": "a" * 64,
                            "fixture_id": "CL-FX-002",
                            "outcome": "success",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        os.chmod(path, 0o600)
        manifest = SyntheticFingerprintManifest(path)
        assert manifest.entry("a" * 64).outcome.value == "success"
        with pytest.raises(SyntheticManifestError, match="not_allowlisted"):
            manifest.entry("b" * 64)


def test_private_manifest_fails_closed_on_permissions_and_invalid_json() -> None:
    with pytest.raises(SyntheticManifestError, match="outside_boundary"):
        SyntheticFingerprintManifest(Path("relative-manifest.json"))
    with tempfile.TemporaryDirectory(prefix="colacci-law-slice4-unit-", dir="/tmp") as directory:
        path = Path(directory) / "manifest.json"
        path.write_text("{}", encoding="utf-8")
        os.chmod(path, 0o644)
        with pytest.raises(SyntheticManifestError, match="permissions_invalid"):
            SyntheticFingerprintManifest(path)
        os.chmod(path, 0o600)
        with pytest.raises(SyntheticManifestError, match="synthetic_manifest_invalid"):
            SyntheticFingerprintManifest(path)


@pytest.mark.parametrize(
    "value,code", [("not-a-number", "invalid_content_length"), ("0", "empty_upload")]
)
def test_content_length_rejects_invalid_or_empty_values(value: str, code: str) -> None:
    with pytest.raises(UploadRequestError, match=code):
        require_bounded_content_length(value, maximum=10)


def test_audio_boundary_rejects_invalid_shape_and_declared_type() -> None:
    body, _ = multipart()
    with pytest.raises(UploadRequestError, match="invalid_multipart"):
        parse_audio_multipart(body, content_type="multipart/form-data", max_media_bytes=1024)
    with pytest.raises(UploadRequestError, match="invalid_multipart"):
        parse_audio_multipart(
            b'filename="generated.wav"',
            content_type="multipart/form-data; boundary=slice4-test-boundary",
            max_media_bytes=1024,
        )
    with pytest.raises(UploadRequestError, match="declared_media_mismatch"):
        parse_audio_multipart(
            body.replace(b"audio/wav", b"audio/mpeg"),
            content_type="multipart/form-data; boundary=slice4-test-boundary",
            max_media_bytes=1024,
        )


def test_upload_state_enum_includes_named_terminal_states() -> None:
    assert {
        UploadState.VALIDATION_FAILED,
        UploadState.TRANSCRIPTION_FAILED,
        UploadState.ANALYSIS_FAILED,
        UploadState.CANCELLED,
        UploadState.DELETION_FAILED,
    } <= set(UploadState)
