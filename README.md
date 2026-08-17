# Colacci Law Call Review — Slice 0

This repository is the synthetic-only application foundation. It provides the API, worker,
React web shell, PostgreSQL database, migration baseline, configuration safety rails, and
offline test surface. It contains no call analysis, transcript fixture, real recording,
Broadvoice contract, live AI integration, or cloud infrastructure.

The sole roadmap and next-steps source is
`/Users/michaelfuscoletti/Desktop/colacci_law_next_steps.md`. Do not add a repository-level
`NEXT_STEPS.md`.

## Prerequisites

- Docker Engine 29.7.2 or compatible and Docker Compose 5.3.1 or compatible.
- `make` and a POSIX shell.
- Internet access is required only for the first image/dependency download and the optional
  live advisory audit. After `make bootstrap`, linting, type checks, tests, integration tests,
  migrations, secret scanning, and smoke checks use only pinned local images and the local
  Docker network.

Host Python and Node are not required. Their exact container versions are Python 3.13.5,
Node.js 22.18.0, npm 10.9.3, and PostgreSQL 17.6 on Alpine 3.22.

## Start from a clean checkout

```bash
make bootstrap
make dev
make smoke
```

Open [http://localhost:15173](http://localhost:15173). The dashboard must always display
**Synthetic demo data**. Local endpoints are:

- Web: `http://localhost:15173` and `/health`
- API: `http://localhost:18000/health/live` and `/health/ready`
- Worker: `http://localhost:18001/health/live` and `/health/ready`
- PostgreSQL: loopback port `54329`

Stop without deleting the local database:

```bash
make stop
```

Start again with `make dev`. To remove only this project's synthetic containers and local
database volume, use the explicit guarded reset:

```bash
CONFIRM_LOCAL_DATA_DELETE=yes make clean
make bootstrap
make dev
```

## Stable command surface

```bash
make bootstrap          # build pinned images, start PostgreSQL, apply migration 0001
make dev                # start database, migrate, and start API, worker, and web
make lint               # formatting, lint, code security, pins, and secret scan
make typecheck          # strict Python and TypeScript checks
make test               # offline unit/security and web tests
make test-integration   # empty-test-database migration and readiness tests
make smoke              # API, worker, web, dashboard, database, and migration readiness
```

`make audit` is the separately labeled vulnerability-advisory check. It contacts public
advisory/package registries and is therefore not part of the deterministic offline suite.

## Repository map

- `apps/api`: FastAPI service and Alembic migration.
- `apps/worker`: Python worker process with independent health server. No jobs exist yet.
- `apps/web`: React/TypeScript dashboard and health page.
- `packages/config`: shared profiles and fail-closed startup validation.
- `packages/contracts`: only the content-free health contract in Slice 0.
- `packages/database`: database and current-migration readiness.
- `packages/observability`: correlation IDs and allowlisted structured logs.
- `fixtures`: empty synthetic-only boundaries reserved for Slice 1.
- `infrastructure/local`: pinned local containers and test database initialization.
- `docs`: architecture, security, decisions, and runbooks.
- `scripts`: stable command implementation and deterministic scanners.
- `tests`: unit, security, integration, and future contract/end-to-end boundaries.

## Safety behavior

The default profile is `demo`, every real-data switch is false, and only fixture/placeholder
adapters are configured. `staging` and `production` reject fake authentication, placeholder or
missing secrets, local storage, fixture sources/transcribers/analyzers, absent retention,
unauthorized real processing, debug mode, unsafe CORS, and local/example databases.

The API and worker log only allowlisted operational metadata. Access logs are disabled. Request
headers, query strings, error details, database URLs, caller data, audio, and transcript content
cannot enter the application logger.

See [architecture](docs/architecture.md), [technology choices](docs/technology.md),
[configuration rules](docs/configuration.md), [adapter boundaries](docs/adapters.md), and the
[security documentation](docs/security/README.md).
