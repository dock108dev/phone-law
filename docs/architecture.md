# Architecture and repository layout

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
`0004_offline_transcription_readiness`. The web container serves a content-free health artifact and
a persistent synthetic-data banner on every review route.

There is no upload, external source, identity integration, notification, live transcription, or
vendor request. Slice 3A adds only locally generated non-human media outside the repository,
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
- Daily report: deterministic America/New_York cutoff, explicit reconciliation, immutable versions
- Human review: append-only labels/notes paired transactionally with content-free audit events
- Playbooks: immutable structured payload; draft-to-published lifecycle metadata only

The Desktop roadmap is the only next-steps source. This repository intentionally has no
`NEXT_STEPS.md`.
