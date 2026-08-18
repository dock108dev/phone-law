# ADR 0009: local synthetic manual-upload bridge

- Status: implemented for local synthetic acceptance
- Authorization: `OWNER-CHAT-2026-08-18-SLICE-4-LOCAL`
- Documentation refreshed: 2026-08-18

## Decision

Add one local demo page and a narrow authenticated API boundary for exactly two single-item modes:
an allowlisted generated non-human audio file and the existing strict invented transcript-only
artifact. Demo administrators and operations users may submit, view receipts, retry named
retryable failures, and cancel before processing. Reviewers may open completed calls and append
feedback, but cannot access upload operations. Demo operations cannot append feedback or publish a
playbook. Every allowed and denied upload action creates a content-free audit event.

Audio admission is bounded before body buffering, checks one safe filename and declared type,
allocates only an opaque private local object, verifies media content and limits, requires an
allowlisted generated fingerprint, normalizes through the accepted media layer, and selects a
deterministic fixture result. Transcript JSON is validated in full before its first database write
and creates no media object. Both modes enter the accepted immutable call, attempt, transcript,
analysis, daily-report, evidence, feedback, and provenance loop.

## Persistence and lifecycle

Alembic revision `0005_manual_upload_local` adds a content-free receipt and append-only state-event
history. Client submission ID, full internal content fingerprint, and source event are unique.
Receipts retain only safe metadata and opaque internal identifiers; original filenames, paths,
multipart headers, request bodies, transcript text, media content, and credentials are excluded.
The lifecycle supports ready, processing, analyzed, named transcription/analysis failure,
cancelled, and deletion failure. Retry increments the attempt on the same call. Cancellation is
idempotent only before processing. Temporary media deletion is confirmed after success, terminal
failure, cancellation, and unexpected exceptions; a failed deletion is visible and audited.

## Consequences and stop boundary

The bridge remains local, synthetic, single-item, fixture-transcribed, and network-isolated. It
does not add a production queue, cloud storage, SSO, notifications, retention, Broadvoice,
recording capture, remote downloads, client access, or real-data handling. It makes no live CLI or
SDK request. Slice 3B, production Slice 3, and CL-060 remain incomplete. Slice 5 is not started.
