# Architecture and repository layout

Slice 0 is a four-component local foundation:

```text
Browser -> React/Vite web shell
             (no call input)

Health probe -> FastAPI API ----+
Health probe -> Python worker --+--> PostgreSQL 17.6
                                      foundation migration only
```

The API and worker load the same fail-closed settings, operational logger, health contract, and
database readiness code from `packages/`. Both expose liveness without touching the database.
Readiness requires a connection and exact Alembic revision `0001_foundation`. The web container
serves a content-free health artifact and a persistent synthetic-data banner.

No queue, call record, transcript model, analysis pipeline, upload, object content, identity
integration, notification, or vendor request exists. The worker is deliberately only a process
and readiness boundary until a later accepted slice introduces jobs.

Docker Compose publishes every port to loopback only. PostgreSQL is the only stateful service.
The initial `system_metadata` table contains only the non-sensitive schema-purpose marker.

## Shared boundaries

- Configuration: `packages/config`
- Health schema: `packages/contracts/health.schema.json`
- Database readiness: `packages/database`
- Content-free logging: `packages/observability`
- Future adapter seams: documented in `docs/adapters.md`; not implemented in Slice 0

The Desktop roadmap is the only next-steps source. This repository intentionally has no
`NEXT_STEPS.md`.
