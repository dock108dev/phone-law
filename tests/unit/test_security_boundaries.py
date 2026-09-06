from __future__ import annotations

import asyncio
import json
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from apps.api.colacci_api.app import create_app
from apps.api.colacci_api.body_limits import (
    JSON_BODY_MAX_BYTES,
    RequestBodyBoundaryError,
    RequestBodyLimitMiddleware,
)
from apps.api.colacci_api.upload_routes import _safe_upload_error
from packages.config import Settings


def test_validation_failure_never_echoes_input_or_attacker_field_names(caplog):
    app = create_app(Settings(_env_file=None))

    class Input(BaseModel):
        count: int

    # Resolve the local annotation explicitly under postponed annotations.
    async def endpoint(payload):
        return {"count": payload.count}

    endpoint.__annotations__["payload"] = Input
    app.post("/validation-probe")(endpoint)
    with TestClient(app) as client:
        response = client.post(
            "/validation-probe",
            json={"count": "private-validation-sentinel"},
            headers={"X-Correlation-ID": "security-test-001"},
        )
    assert response.status_code == 422
    assert response.json() == {
        "detail": {"error": "request_validation_failed", "correlation_id": "security-test-001"}
    }
    assert "private-validation-sentinel" not in response.text + caplog.text
    assert response.headers["Cache-Control"] == "no-store"
    assert "request_validation_rejected" in caplog.text


@pytest.mark.parametrize("length", [b"-1", b"+10", b"1_000", b"1,2", b"9" * 21])
def test_invalid_lengths_fail_before_body_consumption(length):
    _probe_body([b"{}"], [(b"content-length", length)], expected_status=400, reads=0)


def test_declared_oversize_fails_before_body_consumption():
    _probe_body(
        [b"{}"],
        [(b"content-length", str(JSON_BODY_MAX_BYTES + 1).encode())],
        expected_status=413,
        reads=0,
    )


def test_chunked_body_is_bounded_even_without_content_length():
    _probe_body(
        [b"a" * JSON_BODY_MAX_BYTES, b"b", b"never-consumed"], [], expected_status=413, reads=2
    )


def test_understated_content_length_cannot_bypass_actual_byte_limit():
    _probe_body(
        [b"a" * (JSON_BODY_MAX_BYTES + 1)],
        [(b"content-length", b"1")],
        expected_status=413,
        reads=1,
    )


def test_exact_limit_is_accepted():
    _probe_body([b"a" * JSON_BODY_MAX_BYTES], [], expected_status=200, reads=1)


def _probe_body(chunks, headers, *, expected_status, reads):
    async def run():
        messages = []
        consumed = 0
        delivered = 0

        async def receive():
            nonlocal consumed
            body = chunks[consumed]
            consumed += 1
            return {"type": "http.request", "body": body, "more_body": consumed < len(chunks)}

        async def send(message):
            messages.append(message)

        async def application(scope, receive, send):
            nonlocal delivered
            try:
                while True:
                    message = await receive()
                    delivered += len(message["body"])
                    if not message["more_body"]:
                        break
            except RequestBodyBoundaryError as error:
                # FastAPI/Starlette preserve this exception; uploads must preserve it too.
                assert _safe_upload_error(Mock(), error) is error
                await send({"type": "http.response.start", "status": error.status_code})
                return
            await send({"type": "http.response.start", "status": 200})

        middleware = RequestBodyLimitMiddleware(application, media_max_bytes=20 * 1024 * 1024)
        scope = {
            "type": "http",
            "path": "/api/reviews",
            "method": "POST",
            "headers": headers,
            "state": {"correlation_id": "security-test-002"},
        }
        await middleware(scope, receive, send)
        assert messages[0]["status"] == expected_status
        assert consumed == reads
        assert delivered <= JSON_BODY_MAX_BYTES

    asyncio.run(run())


def test_oversized_json_is_rejected_before_auth_or_database_work(caplog):
    app = create_app(Settings(_env_file=None))
    with TestClient(app) as client:
        response = client.post("/api/playbooks/drafts", content=b"x" * (JSON_BODY_MAX_BYTES + 1))
    assert response.status_code == 413
    assert response.json()["detail"]["error"] == "request_body_too_large"
    assert "authorization_audit_unavailable" not in caplog.text
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_stream_limit_preserves_sanitized_413_through_fastapi(caplog):
    app = create_app(Settings(_env_file=None))
    from fastapi import Request

    async def endpoint(request):
        return json.loads(await request.body())

    endpoint.__annotations__["request"] = Request
    app.post("/stream-probe")(endpoint)
    with TestClient(app) as client:
        response = client.post("/stream-probe", content=iter([b"x" * JSON_BODY_MAX_BYTES, b"y"]))
    assert response.status_code == 413
    assert response.json()["detail"]["error"] == "request_body_too_large"
    assert "http_request_failed" not in caplog.text


def test_unknown_audio_never_reaches_storage_decoder_or_database(monkeypatch):
    from types import SimpleNamespace

    from packages.manual_upload.manifest import SyntheticManifestError
    from packages.manual_upload.request_boundary import UploadRequestError
    from packages.manual_upload.service import ManualUploadService

    service = object.__new__(ManualUploadService)
    service._validate_timestamp = Mock()
    service.settings = SimpleNamespace(manual_upload_manifest_path="unused")
    service.store = Mock()
    service.inspector = Mock()
    service.receipts = Mock()
    manifest = Mock()
    manifest.entry.side_effect = SyntheticManifestError("synthetic_fingerprint_not_allowlisted")
    monkeypatch.setattr(
        "packages.manual_upload.service.SyntheticFingerprintManifest", Mock(return_value=manifest)
    )
    parsed = SimpleNamespace(
        payload=b"RIFF-malicious-unlisted-content",
        metadata=SimpleNamespace(client_submission_id="security-audio-001"),
    )
    with pytest.raises(UploadRequestError, match="synthetic_fingerprint_not_allowlisted"):
        service.submit_audio(parsed, principal=Mock())
    service.store.allocate.assert_not_called()
    service.inspector.inspect.assert_not_called()
    service.receipts.create.assert_not_called()


def test_media_inspection_and_normalization_allow_file_protocol_only(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from packages.media.processing import MediaInspector, MediaNormalizer

    source = tmp_path / "input.wav"
    source.write_bytes(b"RIFF0000WAVE" + bytes(32))
    destination = tmp_path / "output.wav"
    destination.write_bytes(source.read_bytes())
    run = Mock(
        return_value=SimpleNamespace(
            stdout=json.dumps(
                {
                    "format": {"format_name": "wav", "duration": "1"},
                    "streams": [
                        {
                            "codec_type": "audio",
                            "codec_name": "pcm_s16le",
                            "sample_rate": "48000",
                            "channels": 1,
                        }
                    ],
                }
            )
        )
    )
    monkeypatch.setattr("packages.media.processing.subprocess.run", run)
    inspector = MediaInspector(max_bytes=1024, max_duration_seconds=60, allowed_root=tmp_path)
    inspection = inspector.inspect(source, artifact_id="security-artifact")
    store = Mock()
    store.allocate.return_value = (SimpleNamespace(object_id="output"), destination)
    store.resolve.return_value = source
    normalizer = MediaNormalizer(store=store, inspector=inspector)
    normalizer.normalize(SimpleNamespace(object_id="input"), inspection)
    assert run.call_count == 3  # Initial probe, normalization, output probe.
    for call in run.call_args_list:
        arguments = call.args[0]
        index = arguments.index("-protocol_whitelist")
        assert arguments[index + 1] == "file"
        if "-i" in arguments:
            assert index < arguments.index("-i")


def test_body_rejection_preserves_configured_logging_level():
    import logging

    app = create_app(Settings(_env_file=None, log_level="ERROR"))
    with TestClient(app) as client:
        response = client.post("/api/playbooks/drafts", content=b"x" * (JSON_BODY_MAX_BYTES + 1))
    assert response.status_code == 413
    assert logging.getLogger("colacci.api").level == logging.ERROR
