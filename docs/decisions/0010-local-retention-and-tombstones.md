# ADR 0010: Local retention destruction and content-free tombstones

- Status: Accepted for Slice 5A local synthetic use
- Date: 2026-08-19
- Authority: `OWNER-CHAT-2026-08-19-LOCAL-FIRST-API-LAST`

## Context

Accepted transcripts, analyses, reports, feedback, playbooks, audit events, and media metadata are immutable under ordinary application and database operations. Slice 5A must also prove policy-driven synthetic content destruction, bounded retry, restart recovery, media cleanup, and auditable tombstones. Silently editing accepted output or broadly weakening database triggers would break the accepted provenance contract.

## Decision

Keep every ordinary immutability trigger active. Redefine the shared trigger functions to permit a change only while the current transaction holds the exact custom PostgreSQL setting `colacci.retention_authorized = slice5a-local-only`.

Only `LocalOperationsRepository` sets that transaction-local value. It accepts a typed `DeletionJob`, chooses from a closed resource enum, and runs a hard-coded resource-specific statement. The API never accepts SQL, a table name, a path, a retention context, or a destruction operation from the caller.

The same transaction:

1. destroys or scrubs the content-bearing field;
2. appends a content-free tombstone;
3. transitions the bounded deletion job; and
4. appends a content-free audit event.

Generated media removal is confirmed before the database transaction records success. A failed removal leaves the content job retryable or terminal; it never creates a success tombstone. Audit metadata receives an explicit `retained_exception` tombstone because the local audit stream is append-only.

Tombstones contain only opaque resource type and identifier, configuration version, result, safe exception code, and time. They cannot contain transcript text, notes, names, filenames, paths, phone numbers, request content, credentials, or provider payloads.

## Consequences

- Accepted output stays immutable for every ordinary code path and direct database statement.
- Destruction is narrow, reviewable, database-tested, version-linked, and auditable.
- Scrubbed rows preserve relationship and provenance metadata, avoiding orphaned foreign keys while public repositories hide tombstoned content.
- Deletion jobs can recover from process restart without duplicate destruction.
- Retry is bounded at three attempts and terminal failure remains visible.
- The custom setting is not a production authorization mechanism. Production retention, database roles, backups, legal holds, and deletion approval remain Slice 5B work.

## Rejected alternatives

- Dropping immutability triggers: rejected because it weakens every ordinary write path.
- Hard-deleting the full call graph: rejected because retention periods differ by resource and foreign-key order can silently destroy still-retained evidence.
- Mutating accepted payloads without a tombstone: rejected because it would erase provenance of the destruction decision.
- Storing deleted content in tombstones or backups: rejected because it defeats deletion and expands sensitive retention.
