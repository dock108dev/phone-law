"""Bounded HTTP request parsing without retaining caller filenames or bodies."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser

from packages.contracts.manual_upload import UploadMetadata

MAX_MULTIPART_OVERHEAD = 64 * 1024
EXPECTED_FIELDS = frozenset(
    {
        "client_submission_id",
        "generated_only_attestation",
        "direction",
        "captured_at",
        "language_hint",
        "staff_extension",
    }
)
SAFE_FILENAME = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}\.(wav|mp3|m4a|mp4|mpeg|mpga|webm)$",
    re.IGNORECASE,
)
CONTENT_TYPES = {
    "wav": {"audio/wav", "audio/x-wav"},
    "mp3": {"audio/mpeg"},
    "mpeg": {"audio/mpeg"},
    "mpga": {"audio/mpeg"},
    "m4a": {"audio/mp4", "audio/x-m4a"},
    "mp4": {"audio/mp4", "video/mp4"},
    "webm": {"audio/webm", "video/webm"},
}


class UploadRequestError(ValueError):
    def __init__(self, code: str, *, status_code: int = 422) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True)
class ParsedAudioUpload:
    metadata: UploadMetadata
    payload: bytes
    filename_extension: str
    declared_content_type: str


def require_bounded_content_length(value: str | None, *, maximum: int) -> int:
    if value is None:
        raise UploadRequestError("content_length_required", status_code=411)
    try:
        length = int(value)
    except ValueError as exc:
        raise UploadRequestError("invalid_content_length", status_code=400) from exc
    if length <= 0:
        raise UploadRequestError("empty_upload")
    if length > maximum:
        raise UploadRequestError("upload_body_too_large", status_code=413)
    return length


def parse_audio_multipart(
    body: bytes,
    *,
    content_type: str,
    max_media_bytes: int,
) -> ParsedAudioUpload:
    if len(body) > max_media_bytes + MAX_MULTIPART_OVERHEAD:
        raise UploadRequestError("upload_body_too_large", status_code=413)
    if (
        not content_type.lower().startswith("multipart/form-data;")
        or "boundary=" not in content_type
    ):
        raise UploadRequestError("invalid_multipart", status_code=400)
    raw_filenames = re.findall(rb'filename="([^"]*)"', body)
    if len(raw_filenames) != 1 or any(
        marker in raw_filenames[0] for marker in (b"\\", b"/", b"\x00", b"%00")
    ):
        raise UploadRequestError("unsafe_filename")
    try:
        message = BytesParser(policy=policy.default).parsebytes(
            f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + body
        )
    except (TypeError, ValueError) as exc:
        raise UploadRequestError("invalid_multipart", status_code=400) from exc
    if not message.is_multipart():
        raise UploadRequestError("invalid_multipart", status_code=400)

    fields: dict[str, str] = {}
    file_payload: bytes | None = None
    filename = ""
    declared_content_type = ""
    for part in message.iter_parts():
        if part.is_multipart() or part.get_content_disposition() != "form-data":
            raise UploadRequestError("invalid_multipart", status_code=400)
        name = part.get_param("name", header="content-disposition")
        if not isinstance(name, str) or not name:
            raise UploadRequestError("invalid_multipart", status_code=400)
        if name == "file":
            if file_payload is not None:
                raise UploadRequestError("multiple_files_forbidden")
            raw_disposition = str(part.get("Content-Disposition", ""))
            if any(marker in raw_disposition for marker in ("\\", "/", "\x00", "%00")):
                raise UploadRequestError("unsafe_filename")
            raw_filename = part.get_filename()
            if not isinstance(raw_filename, str):
                raise UploadRequestError("unsafe_filename")
            filename = raw_filename
            declared_content_type = part.get_content_type().lower()
            decoded = part.get_payload(decode=True)
            if not isinstance(decoded, bytes):
                raise UploadRequestError("invalid_multipart", status_code=400)
            file_payload = decoded
            continue
        if name not in EXPECTED_FIELDS or name in fields:
            raise UploadRequestError("unknown_or_duplicate_upload_field")
        decoded = part.get_payload(decode=True)
        if not isinstance(decoded, bytes) or len(decoded) > 256:
            raise UploadRequestError("invalid_upload_metadata")
        try:
            fields[name] = decoded.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise UploadRequestError("invalid_upload_metadata") from exc

    if file_payload is None or set(fields) != EXPECTED_FIELDS:
        raise UploadRequestError("incomplete_single_item_upload")
    if not file_payload:
        raise UploadRequestError("empty_upload")
    if len(file_payload) > max_media_bytes:
        raise UploadRequestError("upload_body_too_large", status_code=413)
    match = SAFE_FILENAME.fullmatch(filename)
    if match is None or ".." in filename or "\x00" in filename or filename.startswith("."):
        raise UploadRequestError("unsafe_filename")
    extension = match.group(1).lower()
    if declared_content_type not in CONTENT_TYPES[extension]:
        raise UploadRequestError("declared_media_mismatch")
    try:
        metadata = UploadMetadata.model_validate_json(
            json.dumps(
                {
                    **fields,
                    "generated_only_attestation": fields["generated_only_attestation"] == "true",
                }
            )
        )
    except ValueError as exc:
        code = (
            "generated_only_attestation_required"
            if fields.get("generated_only_attestation") != "true"
            else "invalid_upload_metadata"
        )
        raise UploadRequestError(code) from exc
    return ParsedAudioUpload(
        metadata=metadata,
        payload=file_payload,
        filename_extension=extension,
        declared_content_type=declared_content_type,
    )


def parse_header_metadata(headers: dict[str, str]) -> UploadMetadata:
    required = {
        "client_submission_id": "x-client-submission-id",
        "generated_only_attestation": "x-generated-only-attestation",
        "direction": "x-upload-direction",
        "captured_at": "x-upload-captured-at",
        "language_hint": "x-upload-language",
        "staff_extension": "x-upload-staff-extension",
    }
    values = {field: headers.get(header) for field, header in required.items()}
    if any(value is None for value in values.values()):
        raise UploadRequestError("incomplete_upload_metadata")
    attestation = values["generated_only_attestation"] == "true"
    try:
        return UploadMetadata.model_validate_json(
            json.dumps({**values, "generated_only_attestation": attestation})
        )
    except ValueError as exc:
        code = (
            "generated_only_attestation_required" if not attestation else "invalid_upload_metadata"
        )
        raise UploadRequestError(code) from exc
