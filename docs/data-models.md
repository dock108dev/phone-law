# Data model and migrations

PostgreSQL 17.6 is the sole durable runtime store. SQLAlchemy table definitions used by current
repositories live in `packages/database/review_schema.py`; Alembic history under
`apps/api/migrations/versions` is the schema authority for creating or upgrading a database. The
current required revision is `0006_local_operations`, enforced by API/worker readiness.

## Persisted domains

| Domain | Tables | Purpose |
|---|---|---|
| Schema state | `system_metadata`, `alembic_version` | Application schema marker and Alembic revision |
| Call ingestion | `calls`, `ingestion_events`, `processing_attempts` | Deterministic call identity, duplicate delivery, and processing state/attempt history |
| Accepted review data | `transcripts`, `analyses`, `playbook_versions` | Strict accepted payloads and their model, prompt, adapter, and playbook provenance |
| Reports and review | `daily_reports`, `daily_report_items`, `review_events`, `audit_events` | Immutable daily snapshots, ordered items, append-only human review, and content-free audit history |
| Media/transcription metadata | `media_artifacts`, `media_lifecycle_events`, `transcription_provider_attempts` | Synthetic media characteristics, cleanup state, and safe transport/usage metadata |
| Manual upload | `manual_upload_receipts`, `manual_upload_state_events` | Idempotent submission identity, visible lifecycle state, cleanup confirmation, and append-only transitions |
| Local operations | `firm_configuration_versions`, `retention_jobs`, `retention_tombstones`, `maintenance_runs`, `backup_restore_drills`, `notification_previews` | Immutable local policy versions, bounded deletion work, safe evidence, and zero-send previews |

JSONB columns store payloads produced after strict Pydantic contract validation. Where JSONB is
rehydrated into response models, the shared database hydration helper rejects coercion and extra
fields. Content fingerprints, source event IDs, report input fingerprints, and unique constraints
provide idempotency at the database boundary.

## Migration sequence

| Revision | Change |
|---|---|
| `0001_foundation` | Creates `system_metadata` and records the initial schema marker |
| `0002_synthetic_review_contracts` | Adds call, ingestion, attempt, transcript, analysis, and playbook persistence plus immutable-record triggers |
| `0003_synthetic_review_experience` | Adds report, report-item, review, and audit history and controlled playbook lifecycle metadata |
| `0004_offline_transcription_readiness` | Adds media lifecycle and provider-attempt metadata |
| `0005_manual_upload_local` | Adds manual-upload receipts and append-only state events |
| `0006_local_operations` | Adds versioned local configuration, retention jobs/tombstones, maintenance evidence, restore drills, previews, and the initial synthetic policy |

Migrations are reversible for test and development verification, but historical revisions are
snapshots. Change current schema through a new migration; do not rewrite an old migration to match
a later contract constant.

## Mutation and retention rules

PostgreSQL triggers reject updates or ordinary deletes for accepted review payloads, report/review
history, audit history, lifecycle events, configuration/tombstone/maintenance evidence, and other
append-only records. Playbook status timestamps may advance through the defined lifecycle, but its
structured rules remain immutable. Retention job progress may change, while its target and policy
version cannot.

The only content-destruction exception is the transaction-scoped local retention path documented
in [Local operations](local-operations.md) and ADR 0010. That path performs a resource-specific
destruction, appends a content-free tombstone and audit event, and never accepts a table name,
storage path, or arbitrary SQL from an API request.

## Safe change workflow

1. Change strict contracts in `packages/contracts` when the payload shape changes.
2. Add an Alembic revision for a relational change and update `review_schema.py` for repository use.
3. Regenerate JSON Schemas with `make generate-contract-schemas` when contracts change.
4. Run `make lint`, `make typecheck`, `make test`, and `make test-integration`.
5. Run `make smoke` after applying the migration to confirm exact revision readiness.
