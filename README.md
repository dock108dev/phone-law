# Colacci Law Call Review

Local synthetic call-review application for deterministic reports, evidence-linked analysis,
reviewer feedback, failure recovery, manual submission of invented artifacts, and local operations.

This repository contains no client data, real recording, production authentication, external
notification, Broadvoice integration, or generally enabled provider request. The separately
gated transcription verification commands are not part of the normal application runtime.

The sole roadmap and status source is
`/Users/michaelfuscoletti/Desktop/colacci_law_next_steps.md`. Do not add a repository-level
`NEXT_STEPS.md`.

## Start locally

Prerequisites are Docker Engine 29.7.2 or compatible, Docker Compose 5.3.1 or compatible, `make`,
a POSIX shell, and `python3` for deterministic fixture/evidence helpers. Application Python,
Node, npm, and project dependencies run only in pinned containers; host Node is not required.

```bash
make bootstrap
make dev
make smoke
make seed-demo-month
```

Open [http://localhost:15173](http://localhost:15173). The UI must always show **Local / synthetic**
and **No client data or live services**.

Stop services without deleting the synthetic database:

```bash
make stop
```

For a guarded project-only reset:

```bash
CONFIRM_LOCAL_DATA_DELETE=yes make clean
```

## Daily engineering commands

| Command | Purpose |
|---|---|
| `make lint` | Format check, Ruff, Bandit, pins, generated schemas, secret scan, and web lint |
| `make typecheck` | Strict Python and TypeScript checks |
| `make test` | Offline Python unit/security tests and web unit tests |
| `make test-integration` | PostgreSQL migration and repository integration tests |
| `make test-e2e` | Disposable seeded reviewer, upload, and operations browser journeys |
| `make build` | Type-check and build the production web bundle |
| `make test-fixtures` | All deterministic analysis fixtures |
| `make test-manual-upload` | Network-isolated invented-artifact lifecycle proof |
| `make test-local-operations` | Network-isolated role, retention, recovery, and cleanup proof |
| `make test-demo-month` | July 2026 deterministic month and reconciliation proof |
| `make generate-contract-schemas` | Regenerate strict JSON Schemas in the pinned offline image |
| `make smoke` | API, worker, web, dashboard, database, and migration readiness |
| `make audit` | Separate online Python/npm vulnerability advisory check |

Run `make help` for the complete stable command surface. Provider-facing live verification is
owner-gated and never part of routine setup, development, or validation.

## Repository map

- `apps/api`: FastAPI routes, application factory, and Alembic migrations.
- `apps/worker`: health/readiness process; no background jobs are currently supported.
- `apps/web`: React/TypeScript application and browser tests.
- `packages/authorization`: authoritative synthetic role-permission policy.
- `packages/config`: shared typed settings and startup safety validation.
- `packages/contracts`: strict models and generated JSON Schemas.
- `packages/database`: bounded persistence repositories and migration readiness.
- `packages/review`: state machine, fixture pipeline, reporting, and transcript import.
- `packages/manual_upload`: request orchestration for allowlisted generated audio and invented JSON.
- `packages/transcription`: offline contracts and separately gated CLI/SDK transports.
- `fixtures`: deterministic invented inputs; no human or client content.
- `scripts`: stable command implementations, evidence checks, and scanners.
- `docs`: developer, architecture, operations, security, and decision documentation.

## Documentation

Start with the [documentation index](docs/README.md), then use:

- [Local development and troubleshooting](docs/runbooks/local-development.md)
- [Architecture](docs/architecture.md)
- [Current implementation sources of truth](docs/ssot.md)
- [Maintainer guide](docs/maintenance.md)
- [Continuous integration](docs/continuous-integration.md)
- [Testing](docs/testing.md)
- [Data model and migrations](docs/data-models.md)
- [Configuration](docs/configuration.md)
- [Local operations](docs/local-operations.md)
- [Security](docs/security/README.md)
- [Error handling and incident diagnosis](docs/runbooks/error-handling.md)

All routine tests, migrations, smoke checks, and application flows use deterministic synthetic
data and no live AI, telephony, email, cloud storage, or identity service.
