# Architecture and repository layout

## Slice 5A local operations control plane

The API now has a content-free local operations router backed by immutable configuration versions,
restart-safe retention jobs, append-only tombstones, maintenance evidence, disposable restore
drills, and notification previews with zero external attempts. The browser exposes the same safe
controls to demo administrators and operations users and returns a sanitized denial to reviewers.
See [the Slice 5A architecture and operator guide](local-operations.md) and
[ADR 0010](decisions/0010-local-retention-and-tombstones.md).

## Slice 4 local manual-upload bridge

The normal local demo now exposes one authenticated, single-item submission boundary:

```text
administrator/operations -> bounded request -> generated fingerprint allowlist
                                           -> private temporary object -> normalize
                                           -> fixture transcript -> facts-first analysis
invented transcript JSON -> strict whole-artifact validation -----------------+
                                                                            v
reviewer <- append-only feedback <- call/evidence <- immutable daily report
```

The two accepted input shapes are an allowlisted generated non-human audio file and the existing
`transcript-only-artifact-v1` JSON contract. There is no path, URL, folder, batch, manifest,
recording, microphone, remote-download, or arbitrary filesystem import surface. Authorization is
checked before request buffering and allocation. The receipt repository uses unique client
submission IDs, content fingerprints, and source event IDs; its state history is append-only.
Duplicate content returns the existing receipt and never creates a second normalized call or
accepted analysis.

Generated audio is inspected by signature, normalized through the accepted media boundary, then
uses an allowlisted fingerprint to select a deterministic fixture outcome. Retry creates another
attempt for the same call. Cancellation is limited to `ready`. Success, terminal failure, and
cancellation confirm object deletion; deletion failure is a visible audited terminal state.
Transcript-only input is validated before its first receipt write and creates no media object.
Both modes reuse the accepted call, attempt, transcript, analysis, report, evidence, review, and
audit tables. Migration `0005_manual_upload_local` adds only content-free receipts and state
events; accepted transcripts, analyses, feedback, playbooks, and audit history remain immutable.

## Slice 3C local development bridge

`local_dev` is a synthetic-only command-line profile, not an API or worker runtime. It allows
exactly two additional local paths:

```text
generated synthetic media -> openai_cli_local -> shared response converter -> Transcript
invented transcript artifact -> strict import -> existing analysis/report/review contracts
```

The CLI path has one injected child-process boundary. Arguments are an array, the shell is never
used, the executable is allowlisted, the child environment is rebuilt from a small allowlist,
stdout/stderr are bounded, and timeout or cancellation terminates the process group. Only exact
CLI version `1.6.0` with the declared transcription surface is supported. Capability mismatch
selects an offline fallback and cannot install, upgrade, or make a request.

The transcript-only path validates the entire strict artifact before its first database write,
stores no media reference, records source mode and safe transport provenance, and reuses the
existing state machine, fixture analyzer, immutable report, evidence, and feedback flows. Its
deterministic identifiers make repeated import idempotent.

## Slice 3B isolation

The `live_test` path is a separate command-line verification boundary, not part of the
demo application factory. Fresh local synthetic media moves through the restrictive
temporary object store, the gated transcription adapter, strict response validation,
and a disposable evidence database. Downstream analysis and report generation are not
connected. Terminal cleanup removes media and the database while retaining only
sanitized preflight and designated synthetic evaluation evidence outside the repository.

The accepted Slices 0 and 1 remain a four-component local stack. Slice 2 adds an immutable daily
report snapshot, reviewer feedback/audit events, a failure queue, and playbook lifecycle routes:

```text
Browser -> React/Vite synthetic review UI
             report -> call evidence -> feedback

Health probe -> FastAPI API ----+
Health probe -> Python worker --+--> PostgreSQL 17.6
                                      synthetic review + audit contracts
```

The API and worker load the same fail-closed settings, operational logger, health contract, and
database readiness code from `packages/`. Both expose liveness without touching the database.
Readiness requires a connection and exact Alembic revision
`0006_local_operations`. The web container serves a content-free health artifact and
a persistent synthetic-data banner on every review route.

There is no real-data upload, external source, identity integration, notification, live
transcription, or vendor request. Slice 3A adds only locally generated non-human media outside the repository,
restrictive temporary synthetic objects, and mocked response-contract tests. The demo principal
header is allowlisted and accepted only in
demo/test. Fixture processing is an explicit local command; the worker remains a process and
readiness boundary until a later accepted slice introduces jobs.

Docker Compose publishes every port to loopback only. PostgreSQL is the only stateful service.
The database contains only typed synthetic review records and the non-sensitive schema marker.

## Shared boundaries

- Configuration: `packages/config`
- Health schema: `packages/contracts/health.schema.json`
- Database readiness: `packages/database`
- Content-free logging: `packages/observability`
- Fixture adapters: local deterministic implementations; future external seams remain disabled
- Media boundary: content-based ffprobe inspection, channel-preserving ffmpeg normalization, and
  generated-media-only local object storage in demo/test
- Candidate transcription adapter: exact SDK pin, injected mock transport, opaque speaker labels,
  capped deterministic retries, and no normal application factory
- Local CLI development transport: exact CLI/contract declaration, injected command runner,
  restricted child process, shared converter/retries, safe provenance, and offline fallback
- Transcript-only import: invented strict artifact, no media object, deterministic identity, and
  existing downstream review contracts
- Manual upload: one bounded authenticated request, generated fingerprint allowlist, opaque local
  object, content-free receipt, explicit terminal state, retry/cancel/delete, and no external queue
- Local operations: versioned synthetic configuration, server-resolved demo authorization,
  injected-clock retention, bounded deletion, content-free tombstones, safe reconciliation,
  disposable restore drill, and no-op notification preview
- Daily report: deterministic America/New_York cutoff, explicit reconciliation, immutable versions
- Human review: append-only labels/notes paired transactionally with content-free audit events
- Playbooks: immutable structured payload; draft-to-published lifecycle metadata only

The Desktop roadmap is the only next-steps source. This repository intentionally has no
`NEXT_STEPS.md`.
