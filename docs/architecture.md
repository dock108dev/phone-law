# Architecture and repository layout

The accepted Slice 0 foundation remains a four-component local stack. Slice 1 adds strict review
contracts, deterministic fixture adapters, and append-only review persistence without changing
the dashboard or adding a call-data route:

```text
Browser -> React/Vite web shell
             (no call input)

Health probe -> FastAPI API ----+
Health probe -> Python worker --+--> PostgreSQL 17.6
                                      synthetic review contracts
```

The API and worker load the same fail-closed settings, operational logger, health contract, and
database readiness code from `packages/`. Both expose liveness without touching the database.
Readiness requires a connection and exact Alembic revision
`0002_synthetic_review_contracts`. The web container
serves a content-free health artifact and a persistent synthetic-data banner.

No queue, upload, object content, identity integration, notification, report, reviewer workflow,
or vendor request exists. Fixture processing is an explicit local command; the worker remains a
process and readiness boundary until a later accepted slice introduces jobs.

Docker Compose publishes every port to loopback only. PostgreSQL is the only stateful service.
The database contains only typed synthetic review records and the non-sensitive schema marker.

## Shared boundaries

- Configuration: `packages/config`
- Health schema: `packages/contracts/health.schema.json`
- Database readiness: `packages/database`
- Content-free logging: `packages/observability`
- Fixture adapters: local deterministic implementations; future external seams remain disabled

The Desktop roadmap is the only next-steps source. This repository intentionally has no
`NEXT_STEPS.md`.
