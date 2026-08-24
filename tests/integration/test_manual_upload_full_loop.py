from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from apps.api.colacci_api import create_app
from packages.config import Settings
from packages.contracts.manual_upload import UploadState
from packages.contracts.media import MediaDeletionEvent, MediaErrorClass, MediaLifecycleState
from packages.database.manual_uploads import ManualUploadRepository
from packages.database.review_schema import (
    analyses,
    audit_events,
    calls,
    manual_upload_receipts,
    manual_upload_state_events,
    processing_attempts,
)
from packages.media.store import LocalSyntheticObjectStore, SyntheticObjectStoreError
from packages.review.fixtures import FixtureAnalyzer

pytestmark = pytest.mark.integration
ROOT = Path("/tmp/colacci-law-slice4-local")
GENERATED = ROOT / "generated"


def audio_form(submission_id: str) -> dict[str, str]:
    return {
        "client_submission_id": submission_id,
        "generated_only_attestation": "true",
        "direction": "inbound",
        "captured_at": "2026-08-18T04:00:00Z",
        "language_hint": "en",
        "staff_extension": "SYN-104",
    }


def transcript_headers(submission_id: str) -> dict[str, str]:
    return {
        "X-Demo-Principal": "demo-operations",
        "Content-Type": "application/json",
        "X-Client-Submission-ID": submission_id,
        "X-Generated-Only-Attestation": "true",
        "X-Upload-Direction": "inbound",
        "X-Upload-Captured-At": "2026-08-17T14:00:00Z",
        "X-Upload-Language": "en",
        "X-Upload-Staff-Extension": "SYN-104",
    }


def post_audio(
    client: TestClient,
    filename: str,
    submission_id: str,
    principal: str = "demo-admin",
    metadata_overrides: dict[str, str] | None = None,
) -> object:
    payload = (GENERATED / filename).read_bytes()
    metadata = audio_form(submission_id)
    metadata.update(metadata_overrides or {})
    return client.post(
        "/api/uploads/audio",
        headers={"X-Demo-Principal": principal},
        data=metadata,
        files={"file": (filename, payload, "audio/wav")},
    )


def receipt_count(app: object) -> int:
    with app.state.engine.connect() as connection:
        return int(
            connection.execute(
                sa.select(sa.func.count()).select_from(manual_upload_receipts)
            ).scalar_one()
        )


def test_manual_upload_authorization_idempotency_retry_cancel_and_review_loop() -> None:
    settings = Settings(_env_file=None, app_profile="test")
    app = create_app(settings)
    transcript_payload = (GENERATED / "invented-transcript.json").read_bytes()
    with TestClient(app) as client:
        denied = post_audio(
            client,
            "generated-success.wav",
            "reviewer-denied-00000001",
            principal="demo-reviewer",
        )
        assert denied.status_code == 403

        accepted = post_audio(client, "generated-success.wav", "admin-success-0000000001")
        assert accepted.status_code == 201
        receipt = accepted.json()
        assert receipt["state"] == "ready"
        upload_id = receipt["upload_id"]

        same_submission = post_audio(client, "generated-success.wav", "admin-success-0000000001")
        assert same_submission.status_code == 200
        assert same_submission.json()["upload_id"] == upload_id
        assert same_submission.json()["duplicate"] is True

        same_content = post_audio(client, "generated-success.wav", "admin-success-0000000002")
        assert same_content.status_code == 200
        assert same_content.json()["upload_id"] == upload_id

        conflict = post_audio(client, "generated-retry.wav", "admin-success-0000000001")
        assert conflict.status_code == 409
        assert conflict.json()["detail"]["error"] == "submission_content_conflict"

        processed = client.post(
            f"/api/uploads/{upload_id}/process",
            headers={"X-Demo-Principal": "demo-admin"},
        )
        assert processed.status_code == 200
        analyzed = processed.json()
        assert analyzed["state"] == "analyzed"
        assert analyzed["attempt_number"] == 1
        assert analyzed["deletion_confirmed"] is True
        call_id = analyzed["call_id"]

        report = client.get(
            "/api/reports/2026-08-18",
            headers={"X-Demo-Principal": "demo-reviewer"},
        )
        assert report.status_code == 200
        report_call_ids = {
            item["call_id"] for section in report.json()["sections"] for item in section["items"]
        }
        assert call_id in report_call_ids

        detail = client.get(f"/api/calls/{call_id}", headers={"X-Demo-Principal": "demo-reviewer"})
        assert detail.status_code == 200
        detail_payload = detail.json()
        finding_id = detail_payload["findings"][0]["finding_id"]
        feedback = client.post(
            f"/api/analyses/{detail_payload['analysis_id']}/reviews",
            headers={"X-Demo-Principal": "demo-reviewer"},
            json={"label": "correct", "finding_id": finding_id, "note": None},
        )
        assert feedback.status_code == 201
        refreshed = client.get(
            f"/api/calls/{call_id}", headers={"X-Demo-Principal": "demo-reviewer"}
        )
        assert len(refreshed.json()["review_history"]) == 1

        transcript = client.post(
            "/api/uploads/transcript",
            headers=transcript_headers("operations-transcript-0001"),
            content=transcript_payload,
        )
        assert transcript.status_code == 201
        assert transcript.json()["state"] == "analyzed"
        assert transcript.json()["deletion_confirmed"] is True
        transcript_call_id = transcript.json()["call_id"]
        duplicate_transcript = client.post(
            "/api/uploads/transcript",
            headers=transcript_headers("operations-transcript-0002"),
            content=transcript_payload,
        )
        assert duplicate_transcript.status_code == 200
        assert duplicate_transcript.json()["call_id"] == transcript_call_id

        retry_upload = post_audio(
            client, "generated-retry.wav", "operations-retry-0000001", "demo-operations"
        )
        retry_id = retry_upload.json()["upload_id"]
        first_attempt = client.post(
            f"/api/uploads/{retry_id}/process",
            headers={"X-Demo-Principal": "demo-operations"},
        )
        assert first_attempt.json()["state"] == "transcription_failed"
        assert first_attempt.json()["retryable"] is True
        retry_call_id = first_attempt.json()["call_id"]
        second_attempt = client.post(
            f"/api/uploads/{retry_id}/retry",
            headers={"X-Demo-Principal": "demo-operations"},
        )
        assert second_attempt.json()["state"] == "analyzed"
        assert second_attempt.json()["attempt_number"] == 2
        assert second_attempt.json()["call_id"] == retry_call_id
        assert second_attempt.json()["deletion_confirmed"] is True

        cancel_upload = post_audio(client, "generated-cancel.wav", "admin-cancel-0000000001")
        cancel_id = cancel_upload.json()["upload_id"]
        cancelled = client.delete(
            f"/api/uploads/{cancel_id}", headers={"X-Demo-Principal": "demo-admin"}
        )
        assert cancelled.json()["state"] == "cancelled"
        assert cancelled.json()["deletion_confirmed"] is True
        cancelled_again = client.delete(
            f"/api/uploads/{cancel_id}", headers={"X-Demo-Principal": "demo-admin"}
        )
        assert cancelled_again.json()["state"] == "cancelled"

        for method, path in (
            ("get", "/api/uploads"),
            ("get", f"/api/uploads/{upload_id}"),
            ("post", f"/api/uploads/{retry_id}/retry"),
            ("delete", f"/api/uploads/{cancel_id}"),
        ):
            response = getattr(client, method)(path, headers={"X-Demo-Principal": "demo-reviewer"})
            assert response.status_code == 403

    engine = app.state.engine
    with engine.connect() as connection:
        assert (
            connection.execute(
                sa.select(sa.func.count()).select_from(manual_upload_receipts)
            ).scalar_one()
            == 4
        )
        assert (
            connection.execute(
                sa.select(sa.func.count()).select_from(calls).where(calls.c.id == call_id)
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                sa.select(sa.func.count())
                .select_from(analyses)
                .where(analyses.c.call_id == call_id)
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                sa.select(sa.func.count())
                .select_from(processing_attempts)
                .where(processing_attempts.c.call_id == retry_call_id)
            ).scalar_one()
            == 2
        )
        assert (
            connection.execute(
                sa.select(sa.func.count()).select_from(manual_upload_state_events)
            ).scalar_one()
            >= 19
        )
    with pytest.raises(DBAPIError, match="immutable"), engine.begin() as connection:
        connection.execute(
            manual_upload_state_events.update()
            .where(manual_upload_state_events.c.upload_id == upload_id)
            .values(diagnostic_code="mutation_forbidden")
        )
    objects = settings.manual_upload_root
    assert not objects.exists() or not any(objects.iterdir())


def test_transcript_route_rejects_malformed_input_without_receipt() -> None:
    settings = Settings(_env_file=None, app_profile="test")
    app = create_app(settings)
    before = 0
    with app.state.engine.connect() as connection:
        before = int(
            connection.execute(
                sa.select(sa.func.count()).select_from(manual_upload_receipts)
            ).scalar_one()
        )
    with TestClient(app) as client:
        response = client.post(
            "/api/uploads/transcript",
            headers=transcript_headers("operations-invalid-00001"),
            content=json.dumps({"artifact_version": "unsupported"}),
        )
    assert response.status_code == 422
    with app.state.engine.connect() as connection:
        after = int(
            connection.execute(
                sa.select(sa.func.count()).select_from(manual_upload_receipts)
            ).scalar_one()
        )
    assert after == before


def test_invalid_audio_and_request_shapes_leave_no_receipt_or_media() -> None:
    settings = Settings(_env_file=None, app_profile="test")
    app = create_app(settings)
    before = receipt_count(app)
    with TestClient(app) as client:
        unallowlisted = bytearray((GENERATED / "generated-cancel.wav").read_bytes())
        unallowlisted[-1] ^= 1
        cases = (
            post_audio(
                client,
                "generated-success.wav",
                "invalid-attestation-0001",
                metadata_overrides={"generated_only_attestation": "false"},
            ),
            client.post(
                "/api/uploads/audio",
                headers={"X-Demo-Principal": "demo-admin"},
                data=audio_form("empty-upload-0000000001"),
                files={"file": ("generated.wav", b"", "audio/wav")},
            ),
            client.post(
                "/api/uploads/audio",
                headers={
                    "X-Demo-Principal": "demo-admin",
                    "Content-Type": "multipart/form-data; boundary=missing",
                },
                content=b"not-a-multipart-body",
            ),
            client.post(
                "/api/uploads/audio",
                headers={"X-Demo-Principal": "demo-admin"},
                data=audio_form("unsupported-media-00001"),
                files={"file": ("generated.wav", b"generated non-media", "audio/wav")},
            ),
            post_audio(client, "generated-corrupt.wav", "corrupt-media-000000001"),
            post_audio(client, "generated-overlong.wav", "overlong-media-00000001"),
            client.post(
                "/api/uploads/audio",
                headers={"X-Demo-Principal": "demo-admin"},
                data=audio_form("unallowlisted-media-0001"),
                files={"file": ("generated.wav", bytes(unallowlisted), "audio/wav")},
            ),
            client.post(
                "/api/uploads/audio",
                headers={"X-Demo-Principal": "demo-admin"},
                data=audio_form("unsafe-name-0000000001"),
                files={"file": ("../generated.wav", b"RIFF0000WAVE", "audio/wav")},
            ),
            post_audio(
                client,
                "generated-success.wav",
                "language-mismatch-00001",
                metadata_overrides={"language_hint": "es"},
            ),
            post_audio(
                client,
                "generated-success.wav",
                "direction-invalid-000001",
                metadata_overrides={"direction": "sideways"},
            ),
            post_audio(
                client,
                "generated-success.wav",
                "timestamp-invalid-000001",
                metadata_overrides={"captured_at": "2030-01-01T00:00:00Z"},
            ),
        )
        oversized = client.post(
            "/api/uploads/audio",
            headers={
                "X-Demo-Principal": "demo-admin",
                "Content-Length": str(settings.media_max_bytes + 65_537),
                "Content-Type": "multipart/form-data; boundary=bounded",
            },
            content=b"x",
        )
    for response in (*cases, oversized):
        assert response.status_code in {400, 413, 422}
        detail = response.json()["detail"]
        assert set(detail) == {"error", "correlation_id"}
        assert "/" not in detail["error"]
    assert receipt_count(app) == before
    assert not settings.manual_upload_root.exists() or not any(
        settings.manual_upload_root.iterdir()
    )


def test_named_terminal_and_analysis_failures_retry_and_cancel_race() -> None:
    settings = Settings(_env_file=None, app_profile="test")
    app = create_app(settings)
    with TestClient(app) as client:
        terminal = post_audio(
            client,
            "generated-transcription-terminal.wav",
            "terminal-transcription-0001",
            principal="demo-operations",
        ).json()
        terminal_result = client.post(
            f"/api/uploads/{terminal['upload_id']}/process",
            headers={"X-Demo-Principal": "demo-operations"},
        )
        assert terminal_result.status_code == 200
        assert terminal_result.json()["state"] == "transcription_failed"
        assert terminal_result.json()["retryable"] is False
        assert terminal_result.json()["deletion_confirmed"] is True
        assert (
            client.post(
                f"/api/uploads/{terminal['upload_id']}/retry",
                headers={"X-Demo-Principal": "demo-operations"},
            ).status_code
            == 409
        )
        assert (
            client.delete(
                f"/api/uploads/{terminal['upload_id']}",
                headers={"X-Demo-Principal": "demo-admin"},
            ).status_code
            == 409
        )

        analysis_retry = post_audio(
            client,
            "generated-analysis-retry.wav",
            "analysis-retry-000000001",
            principal="demo-admin",
        ).json()
        first = client.post(
            f"/api/uploads/{analysis_retry['upload_id']}/process",
            headers={"X-Demo-Principal": "demo-admin"},
        ).json()
        assert first["state"] == "analysis_failed"
        assert first["retryable"] is True
        retry_call_id = first["call_id"]
        second = client.post(
            f"/api/uploads/{analysis_retry['upload_id']}/retry",
            headers={"X-Demo-Principal": "demo-operations"},
        ).json()
        assert second["state"] == "analyzed"
        assert second["attempt_number"] == 2
        assert second["call_id"] == retry_call_id
        assert second["deletion_confirmed"] is True

        detail = client.get(
            f"/api/calls/{retry_call_id}",
            headers={"X-Demo-Principal": "demo-operations"},
        ).json()
        operations_feedback = client.post(
            f"/api/analyses/{detail['analysis_id']}/reviews",
            headers={"X-Demo-Principal": "demo-operations"},
            json={
                "label": "correct",
                "finding_id": detail["findings"][0]["finding_id"],
                "note": None,
            },
        )
        assert operations_feedback.status_code == 403

        analysis_terminal = post_audio(
            client,
            "generated-analysis-terminal.wav",
            "analysis-terminal-0000001",
        ).json()
        terminal_analysis = client.post(
            f"/api/uploads/{analysis_terminal['upload_id']}/process",
            headers={"X-Demo-Principal": "demo-admin"},
        ).json()
        assert terminal_analysis["state"] == "analysis_failed"
        assert terminal_analysis["retryable"] is False
        assert terminal_analysis["deletion_confirmed"] is True
    assert not settings.manual_upload_root.exists() or not any(
        settings.manual_upload_root.iterdir()
    )


def test_object_store_database_and_unexpected_failures_are_sanitized_logged_and_cleaned(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = Settings(_env_file=None, app_profile="test")
    app = create_app(settings)
    before = receipt_count(app)
    with TestClient(app) as client:
        with monkeypatch.context() as patch:

            def fail_allocate(_store: LocalSyntheticObjectStore, *, artifact_id: str) -> None:
                assert artifact_id
                raise SyntheticObjectStoreError("synthetic_object_store_unavailable")

            patch.setattr(LocalSyntheticObjectStore, "allocate", fail_allocate)
            store_failure = post_audio(
                client,
                "generated-unexpected.wav",
                "object-store-failure-0001",
            )
        assert store_failure.status_code == 422
        assert store_failure.json()["detail"]["error"] == "synthetic_object_store_unavailable"
        assert receipt_count(app) == before

        with monkeypatch.context() as patch:

            def fail_create(_repository: ManualUploadRepository, **_values: object) -> None:
                raise SQLAlchemyError("database unavailable")

            patch.setattr(ManualUploadRepository, "create", fail_create)
            database_failure = post_audio(
                client,
                "generated-unexpected.wav",
                "database-failure-0000001",
            )
        assert database_failure.status_code == 500
        assert database_failure.json()["detail"]["error"] == "manual_upload_failed"
        assert "unexpected_manual_upload_failure" in caplog.text
        assert receipt_count(app) == before

        unexpected = post_audio(
            client,
            "generated-unexpected.wav",
            "unexpected-failure-000001",
        ).json()
        with monkeypatch.context() as patch:

            def fail_analysis(
                _analyzer: FixtureAnalyzer, _fixture_id: str, _transcript: object
            ) -> None:
                raise RuntimeError("deliberate unexpected failure")

            patch.setattr(FixtureAnalyzer, "extract_facts", fail_analysis)
            result = client.post(
                f"/api/uploads/{unexpected['upload_id']}/process",
                headers={"X-Demo-Principal": "demo-admin"},
            )
        assert result.status_code == 500
        assert result.json()["detail"]["error"] == "manual_upload_failed"
        stored = ManualUploadRepository(app.state.engine).get(unexpected["upload_id"])
        assert stored is not None
        assert stored.receipt.state is UploadState.ANALYSIS_FAILED
        assert stored.receipt.diagnostic_code == "unexpected_processing_failure"
        assert stored.receipt.deletion_confirmed is True
        assert "unexpected_audio_processing_failure" in caplog.text
    assert not settings.manual_upload_root.exists() or not any(
        settings.manual_upload_root.iterdir()
    )


def test_deletion_failure_is_visible_audited_and_leaves_no_test_orphan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(_env_file=None, app_profile="test")
    app = create_app(settings)
    with TestClient(app) as client:
        upload = post_audio(
            client,
            "generated-deletion-failure.wav",
            "deletion-failure-0000001",
        ).json()
        stored = ManualUploadRepository(app.state.engine).get(upload["upload_id"])
        assert (
            stored is not None and stored.object_id is not None and stored.artifact_id is not None
        )

        with monkeypatch.context() as patch:

            def fail_delete(
                _store: LocalSyntheticObjectStore, reference: object
            ) -> MediaDeletionEvent:
                return MediaDeletionEvent(
                    event_id="f" * 32,
                    artifact_id=stored.artifact_id,
                    object_id=stored.object_id,
                    state=MediaLifecycleState.DELETED,
                    deletion_confirmed=False,
                    error_class=MediaErrorClass.MEDIA_DELETION_FAILED,
                    occurred_at=datetime.now(UTC),
                )

            patch.setattr(LocalSyntheticObjectStore, "delete", fail_delete)
            failed = client.delete(
                f"/api/uploads/{upload['upload_id']}",
                headers={"X-Demo-Principal": "demo-admin"},
            )
        assert failed.status_code == 200
        assert failed.json()["state"] == "deletion_failed"
        assert failed.json()["deletion_confirmed"] is False
        with app.state.engine.connect() as connection:
            assert (
                connection.execute(
                    sa.select(sa.func.count())
                    .select_from(audit_events)
                    .where(
                        audit_events.c.action == "upload_deletion_failed",
                        audit_events.c.result == "failed",
                    )
                ).scalar_one()
                >= 1
            )
        (settings.manual_upload_root / stored.object_id).unlink(missing_ok=True)
    assert not settings.manual_upload_root.exists() or not any(
        settings.manual_upload_root.iterdir()
    )
