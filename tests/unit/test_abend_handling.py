from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from apps.api.colacci_api import create_app
from apps.api.colacci_api.upload_routes import _raise_safe_upload_error
from packages.config import Settings
from packages.manual_upload.request_boundary import UploadRequestError
from packages.manual_upload.service import ManualUploadService
from packages.observability.logging import OperationalLogger
from scripts import cleanup_manual_upload_assets, secret_scan


def test_unexpected_api_failure_has_safe_diagnostics_and_headers(caplog):
    app = create_app(Settings(_env_file=None))

    @app.get("/fault")
    def fault():
        raise RuntimeError("private client content and credentials")

    with TestClient(app) as client:
        for _ in range(2):
            response = client.get(
                "/fault",
                headers={
                    "X-Correlation-ID": "abend-request-001",
                    "Origin": "http://localhost:15173",
                },
            )
            assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:15173"
            assert response.headers["Access-Control-Expose-Headers"] == "X-Correlation-ID"
            assert response.status_code == 500
            assert response.json()["detail"] == {
                "error": "internal_error",
                "correlation_id": "abend-request-001",
            }
            assert response.headers["X-Correlation-ID"] == "abend-request-001"
            assert response.headers["Cache-Control"] == "no-store"
            assert response.headers["X-Content-Type-Options"] == "nosniff"
    records = [json.loads(line) for line in caplog.messages if '"event"' in line]
    errors = [record for record in records if record["event"] == "http_request_failed"]
    assert len(errors) == 2
    assert errors[0]["exception_type"] == "RuntimeError"
    assert any("test_abend_handling.py" in frame for frame in errors[0]["exception_frames"])
    assert "private client" not in caplog.text


def test_upload_programming_lookup_errors_are_not_misreported_as_missing(caplog):
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(operational_logger=OperationalLogger("api"))),
        state=SimpleNamespace(correlation_id="abend-request-002"),
    )
    for error in (KeyError("private"), IndexError("private")):
        with pytest.raises(Exception) as caught:
            _raise_safe_upload_error(request, error)
        assert caught.value.status_code == 500
    with pytest.raises(Exception) as missing:
        _raise_safe_upload_error(request, LookupError("upload_receipt_not_found"))
    assert missing.value.status_code == 404
    assert "private" not in caplog.text


def test_cleanup_attempts_all_distinct_references_and_escalates(caplog):
    service = object.__new__(ManualUploadService)
    service.operational_logger = OperationalLogger("manual_upload")
    service.correlation_id = "abend-cleanup-001"
    service.store = Mock()
    service.store.delete.side_effect = [
        SimpleNamespace(deletion_confirmed=False),
        SimpleNamespace(deletion_confirmed=True),
    ]
    source = SimpleNamespace(object_id="one")
    retained = SimpleNamespace(object_id="two")
    with pytest.raises(UploadRequestError) as caught:
        service._delete_references(source, retained)
    assert caught.value.status_code == 500
    assert service.store.delete.call_count == 2
    assert "temporary_media_cleanup_failed" in caplog.text
    service.store.delete.reset_mock(side_effect=True)
    service.store.delete.return_value = SimpleNamespace(deletion_confirmed=True)
    service._delete_references(source, source)
    service.store.delete.assert_called_once_with(source)


def test_secret_scan_fails_closed_for_unreadable_source(tmp_path):
    missing = tmp_path / "missing.py"
    invalid = tmp_path / "invalid.py"
    invalid.write_bytes(b"\xff")
    findings = secret_scan.scan_paths([missing, invalid])
    assert [finding.kind for finding in findings] == ["source_unreadable", "source_unreadable"]


def test_cleanup_script_rejects_failed_extensionless_object_deletion(monkeypatch):
    monkeypatch.setattr(cleanup_manual_upload_assets, "ROOT", Path("/tmp/colacci-law-abend-test"))
    monkeypatch.setattr(
        cleanup_manual_upload_assets.shutil, "rmtree", Mock(side_effect=PermissionError)
    )
    with pytest.raises(SystemExit, match="temporary data may remain"):
        cleanup_manual_upload_assets.main()


def test_worker_framework_failure_logs_sanitized_source_locations(caplog):
    from apps.worker.colacci_worker.main import WorkerHealthServer

    server = object.__new__(WorkerHealthServer)
    server.operational_logger = OperationalLogger("worker")
    try:
        raise RuntimeError("private worker content")
    except RuntimeError:
        server.handle_error(None, None)
    payload = json.loads(caplog.messages[-1])
    assert payload["event"] == "worker_health_request_failed"
    assert payload["exception_type"] == "RuntimeError"
    assert payload["exception_frames"]
    assert "private worker" not in caplog.text


def test_original_processing_fault_is_logged_before_recovery_write_fails(caplog):
    service = object.__new__(ManualUploadService)
    service.operational_logger = OperationalLogger("manual_upload")
    service.correlation_id = "abend-recovery-001"
    service.receipts = Mock()
    from packages.contracts.manual_upload import UploadKind, UploadState

    service.receipts.claim_processing.return_value = SimpleNamespace(
        receipt=SimpleNamespace(
            state=UploadState.PROCESSING, submission_kind=UploadKind.SYNTHETIC_AUDIO
        ),
        object_id="object",
        artifact_id="artifact",
    )
    service._unexpected_audio_failure = Mock(side_effect=RuntimeError("private recovery fault"))
    # Missing settings deliberately triggers an unexpected defect before recovery.
    with pytest.raises(RuntimeError, match="private recovery fault"):
        service.process_audio("upload")
    payload = json.loads(caplog.messages[-1])
    assert payload["event"] == "manual_upload_processing_failed"
    assert payload["exception_type"] == "AttributeError"
    assert "private recovery" not in caplog.text


def test_store_cleanup_failure_is_visible_without_paths(caplog, tmp_path):
    from packages.media.store import LocalSyntheticObjectStore

    store = object.__new__(LocalSyntheticObjectStore)
    path = Mock()
    path.unlink.side_effect = PermissionError("private path")
    store._safe_path = Mock(return_value=path)
    reference = SimpleNamespace(artifact_id="artifact", object_id="a" * 32)
    result = store.delete(reference)
    assert not result.deletion_confirmed
    assert '"event":"media_deletion_failed"' in caplog.text
    assert "private path" not in caplog.text


def test_failed_import_cleans_partial_allocation(tmp_path, monkeypatch):
    from packages.media.store import LocalSyntheticObjectStore

    store = object.__new__(LocalSyntheticObjectStore)
    source, destination = tmp_path / "source", tmp_path / "destination"
    reference = SimpleNamespace(object_id="a" * 32)
    store._assert_approved_source = Mock(return_value=source)
    store.allocate = Mock(return_value=(reference, destination))
    store.delete = Mock()
    monkeypatch.setattr("packages.media.store.shutil.copyfile", Mock(side_effect=OSError("copy")))
    with pytest.raises(OSError, match="copy"):
        store.import_file(source, artifact_id="artifact")
    store.delete.assert_called_once_with(reference)
