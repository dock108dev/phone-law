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
)
