"""Relational schema used by the synthetic review repository."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

metadata = sa.MetaData()

calls = sa.Table(
    "calls",
    metadata,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("fixture_id", sa.String(32), nullable=False),
    sa.Column("source", sa.String(32), nullable=False),
    sa.Column("source_call_id", sa.String(128), nullable=False),
    sa.Column("state", sa.String(40), nullable=False),
    sa.Column("is_synthetic", sa.Boolean, nullable=False),
    sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("normalized_payload", JSONB, nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("source", "source_call_id", name="uq_calls_source_call"),
)

ingestion_events = sa.Table(
    "ingestion_events",
    metadata,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("call_id", sa.String(32), sa.ForeignKey("calls.id"), nullable=False),
    sa.Column("source", sa.String(32), nullable=False),
    sa.Column("source_event_id", sa.String(128), nullable=False),
    sa.Column("fixture_id", sa.String(32), nullable=False),
    sa.Column("disposition", sa.String(32), nullable=False),
    sa.Column("duplicate_delivery_count", sa.Integer, nullable=False, server_default="0"),
    sa.Column("event_payload", JSONB, nullable=False),
    sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("source", "source_event_id", name="uq_ingestion_events_source_event"),
)

processing_attempts = sa.Table(
    "processing_attempts",
    metadata,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("call_id", sa.String(32), sa.ForeignKey("calls.id"), nullable=False),
    sa.Column("attempt_number", sa.Integer, nullable=False),
    sa.Column("state", sa.String(40), nullable=False),
    sa.Column("failure_class", sa.String(64), nullable=True),
    sa.Column("diagnostic_code", sa.String(128), nullable=True),
    sa.Column("retryable", sa.Boolean, nullable=True),
    sa.Column("provenance_payload", JSONB, nullable=False),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    sa.UniqueConstraint("call_id", "attempt_number", name="uq_attempts_call_number"),
)

transcripts = sa.Table(
    "transcripts",
    metadata,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("call_id", sa.String(32), sa.ForeignKey("calls.id"), nullable=False),
    sa.Column("attempt_id", sa.String(32), sa.ForeignKey("processing_attempts.id"), nullable=False),
    sa.Column("language", sa.String(8), nullable=False),
    sa.Column("original_payload", JSONB, nullable=False),
    sa.Column("schema_version", sa.String(64), nullable=False),
    sa.Column("adapter_version", sa.String(128), nullable=False),
    sa.Column("model_version", sa.String(128), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("call_id", name="uq_transcripts_call"),
    sa.UniqueConstraint("attempt_id", name="uq_transcripts_attempt"),
)

analyses = sa.Table(
    "analyses",
    metadata,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("call_id", sa.String(32), sa.ForeignKey("calls.id"), nullable=False),
    sa.Column("attempt_id", sa.String(32), sa.ForeignKey("processing_attempts.id"), nullable=False),
    sa.Column("acceptance_state", sa.String(32), nullable=False),
    sa.Column("original_payload", JSONB, nullable=False),
    sa.Column("schema_version", sa.String(64), nullable=False),
    sa.Column("prompt_version", sa.String(128), nullable=False),
    sa.Column("playbook_version", sa.String(128), nullable=False),
    sa.Column("adapter_version", sa.String(128), nullable=False),
    sa.Column("model_version", sa.String(128), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("acceptance_state = 'accepted'", name="ck_analyses_accepted_only"),
    sa.UniqueConstraint("call_id", name="uq_analyses_call"),
    sa.UniqueConstraint("attempt_id", name="uq_analyses_attempt"),
)

playbook_versions = sa.Table(
    "playbook_versions",
    metadata,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("version", sa.String(128), nullable=False, unique=True),
    sa.Column("status", sa.String(32), nullable=False),
    sa.Column("is_synthetic", sa.Boolean, nullable=False),
    sa.Column("structured_payload", JSONB, nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
)

media_artifacts = sa.Table(
    "media_artifacts",
    metadata,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("call_id", sa.String(32), sa.ForeignKey("calls.id"), nullable=True),
    sa.Column("is_synthetic", sa.Boolean, nullable=False),
    sa.Column("content_hash_reference", sa.String(19), nullable=False),
    sa.Column("media_format", sa.String(16), nullable=False),
    sa.Column("byte_size", sa.BigInteger, nullable=False),
    sa.Column("duration_seconds", sa.Float, nullable=False),
    sa.Column("channel_count", sa.Integer, nullable=False),
    sa.Column("sample_rate_hz", sa.Integer, nullable=False),
    sa.Column("lifecycle_state", sa.String(32), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
)

media_lifecycle_events = sa.Table(
    "media_lifecycle_events",
    metadata,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("artifact_id", sa.String(32), sa.ForeignKey("media_artifacts.id"), nullable=False),
    sa.Column("state", sa.String(32), nullable=False),
    sa.Column("deletion_confirmed", sa.Boolean, nullable=True),
    sa.Column("error_class", sa.String(64), nullable=True),
    sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
)

transcription_provider_attempts = sa.Table(
    "transcription_provider_attempts",
    metadata,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("artifact_id", sa.String(32), sa.ForeignKey("media_artifacts.id"), nullable=False),
    sa.Column("call_id", sa.String(32), sa.ForeignKey("calls.id"), nullable=True),
    sa.Column("attempt_number", sa.Integer, nullable=False),
    sa.Column("adapter_version", sa.String(128), nullable=False),
    sa.Column("model_id", sa.String(128), nullable=False),
    sa.Column("provider_response_version", sa.String(128), nullable=True),
    sa.Column("timestamp_availability", sa.String(32), nullable=True),
    sa.Column("diarization_availability", sa.String(32), nullable=True),
    sa.Column("safe_error_class", sa.String(64), nullable=True),
    sa.Column("retryable", sa.Boolean, nullable=False),
    sa.Column("duration_ms", sa.Float, nullable=False),
    sa.Column("input_tokens", sa.Integer, nullable=True),
    sa.Column("output_tokens", sa.Integer, nullable=True),
    sa.Column("usage_duration_seconds", sa.Float, nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

daily_reports = sa.Table(
    "daily_reports",
    metadata,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("business_date", sa.Date, nullable=False),
    sa.Column("version", sa.Integer, nullable=False),
    sa.Column("status", sa.String(32), nullable=False),
    sa.Column("input_fingerprint", sa.String(64), nullable=False),
    sa.Column("cutoff_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("snapshot_payload", JSONB, nullable=False),
    sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("business_date", "version", name="uq_daily_reports_date_version"),
    sa.UniqueConstraint("business_date", "input_fingerprint", name="uq_daily_reports_inputs"),
)

daily_report_items = sa.Table(
    "daily_report_items",
    metadata,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("report_id", sa.String(32), sa.ForeignKey("daily_reports.id"), nullable=False),
    sa.Column("call_id", sa.String(32), sa.ForeignKey("calls.id"), nullable=False),
    sa.Column("analysis_id", sa.String(32), sa.ForeignKey("analyses.id"), nullable=True),
    sa.Column("section", sa.String(64), nullable=False),
    sa.Column("position", sa.Integer, nullable=False),
    sa.Column("item_payload", JSONB, nullable=False),
    sa.UniqueConstraint("report_id", "section", "position", name="uq_report_items_position"),
)

review_events = sa.Table(
    "review_events",
    metadata,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("analysis_id", sa.String(32), sa.ForeignKey("analyses.id"), nullable=False),
    sa.Column("finding_id", sa.String(128), nullable=True),
    sa.Column("label", sa.String(32), nullable=False),
    sa.Column("note", sa.Text, nullable=True),
    sa.Column("principal_id", sa.String(64), nullable=False),
    sa.Column("role", sa.String(32), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

audit_events = sa.Table(
    "audit_events",
    metadata,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("principal_id", sa.String(64), nullable=False),
    sa.Column("role", sa.String(32), nullable=False),
    sa.Column("action", sa.String(128), nullable=False),
    sa.Column("target_type", sa.String(64), nullable=False),
    sa.Column("target_id", sa.String(128), nullable=False),
    sa.Column("result", sa.String(64), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

manual_upload_receipts = sa.Table(
    "manual_upload_receipts",
    metadata,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("client_submission_id", sa.String(64), nullable=False),
    sa.Column("source_event_id", sa.String(128), nullable=False),
    sa.Column("call_id", sa.String(32), sa.ForeignKey("calls.id"), nullable=True),
    sa.Column("submission_kind", sa.String(32), nullable=False),
    sa.Column("is_synthetic", sa.Boolean, nullable=False),
    sa.Column("content_fingerprint", sa.String(64), nullable=False),
    sa.Column("language_hint", sa.String(8), nullable=False),
    sa.Column("direction", sa.String(16), nullable=False),
    sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("staff_extension", sa.String(16), nullable=False),
    sa.Column("principal_id", sa.String(64), nullable=False),
    sa.Column("role", sa.String(32), nullable=False),
    sa.Column("state", sa.String(32), nullable=False),
    sa.Column("attempt_number", sa.Integer, nullable=False),
    sa.Column("diagnostic_code", sa.String(64), nullable=True),
    sa.Column("retryable", sa.Boolean, nullable=False),
    sa.Column("object_id", sa.String(32), nullable=True),
    sa.Column("artifact_id", sa.String(32), nullable=True),
    sa.Column("validation_summary", JSONB, nullable=False),
    sa.Column("deletion_confirmed", sa.Boolean, nullable=True),
    sa.Column("adapter_version", sa.String(128), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    sa.UniqueConstraint("client_submission_id", name="uq_manual_upload_submission"),
    sa.UniqueConstraint("content_fingerprint", name="uq_manual_upload_content"),
    sa.UniqueConstraint("source_event_id", name="uq_manual_upload_source_event"),
)

manual_upload_state_events = sa.Table(
    "manual_upload_state_events",
    metadata,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column(
        "upload_id", sa.String(32), sa.ForeignKey("manual_upload_receipts.id"), nullable=False
    ),
    sa.Column("state", sa.String(32), nullable=False),
    sa.Column("attempt_number", sa.Integer, nullable=False),
    sa.Column("diagnostic_code", sa.String(64), nullable=True),
    sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
)
