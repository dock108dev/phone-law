# Colacci Law Call Review — Slice 4 Local

This repository contains the synthetic-only daily review experience and its bounded local
development bridges. It turns deterministic fixtures into an immutable daily report,
evidence-linked call analysis, append-only human feedback, a content-free failure queue, and an
immutable playbook publication lifecycle. Slice 4 adds an authenticated, single-item local bridge
for allowlisted generated non-human audio and the accepted invented transcript-only artifact. It
contains no real recording, unapproved live AI request, Broadvoice contract, notification,
production authentication, retention implementation, or cloud infrastructure.

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

Host Python 3 is used only by deterministic local fixture and evidence helpers; it does not
run the application or install project dependencies. Host Node is not required. The exact
container versions are Python 3.13.5, Node.js 22.18.0, npm 10.9.3, and PostgreSQL 17.6 on
Alpine 3.22.

## Start from a clean checkout

```bash
make bootstrap
make dev
make smoke
```

Seed the local synthetic review data, then open the app:

```bash
make seed-demo
```

Open [http://localhost:15173](http://localhost:15173). Every review view must display
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
make bootstrap          # build pinned images, start PostgreSQL, apply migration 0005
make seed-demo          # idempotently install all fixtures and the immutable daily report
make dev                # start database, migrate, and start API, worker, and web
make lint               # formatting, lint, code security, pins, and secret scan
make typecheck          # strict Python and TypeScript checks
make test               # offline unit/security and web tests
make test-integration   # empty-test-database migration and readiness tests
make test-fixtures      # all 12 deterministic fixtures; report under /tmp
make test-e2e           # disposable seeded browser flow, accessibility, screenshots, log proof
make smoke              # API, worker, web, review shell, database, and migration readiness
make transcription-cli-preflight # inspect the installed CLI without credentials or a request
make test-transcription-cli-offline # network-blocked CLI contracts and transcript-only full loop
make test-manual-upload # network-isolated upload boundary, lifecycle, browser, and evidence proof
```

`make audit` is the separately labeled vulnerability-advisory check. It contacts public
advisory/package registries and is therefore not part of the deterministic offline suite.

The Slice 3C bridge declares exact support for OpenAI CLI `1.6.0` and contract
`openai-cli-audio-transcriptions-v1`. Run `make transcription-cli-preflight` before selecting the
transport. An absent, mismatched, or legacy CLI selects the fixture and transcript-only fallback;
it never triggers installation, upgrade, or a provider request. Sanitized evidence is written
under `/tmp/colacci-law-slice3c/evidence/`.

The Slice 4 page is [http://localhost:15173/uploads](http://localhost:15173/uploads). Demo
administrators and operations users may submit one allowlisted generated audio file or one strict
invented transcript JSON artifact. Reviewers cannot access receipts or upload actions, but may
open completed calls and append feedback. `make test-manual-upload` runs its service and browser
proof on internal-only Docker networks and writes sanitized evidence beneath
`/tmp/colacci-law-slice4-local/evidence/`.

## Repository map

- `apps/api`: FastAPI service and Alembic migration.
- `apps/worker`: Python worker process with independent health server. No jobs exist yet.
- `apps/web`: React/TypeScript daily report, call review, manual upload, failure, and playbook views.
- `packages/config`: shared profiles and fail-closed startup validation.
- `packages/contracts`: strict review models and synchronized versioned JSON Schemas.
- `packages/database`: readiness plus immutable synthetic review persistence.
- `packages/review`: state machine, evidence validation, adapter protocols, fixture pipeline, and
  strict transcript-only import.
- `packages/manual_upload`: strict request parsing, private fingerprint allowlist, and bounded
  local orchestration through the existing immutable review pipeline.
- `packages/transcription`: shared response conversion plus the bounded SDK and local CLI
  transports.
- `packages/observability`: correlation IDs and allowlisted structured logs.
- `fixtures`: the twelve-scenario synthetic manifest and draft synthetic playbook.
- `infrastructure/local`: pinned local containers and test database initialization.
- `docs`: architecture, security, decisions, and runbooks.
- `scripts`: stable command implementation and deterministic scanners.
- `tests`: unit, security, integration, and future contract/end-to-end boundaries.

## Safety behavior

The default profile is `demo`, every real-data switch is false, and only fixture/placeholder
adapters are configured. `staging` and `production` reject fake authentication, placeholder or
missing secrets, local storage, fixture sources/transcribers/analyzers, absent retention,
unauthorized real processing, debug mode, unsafe CORS, and local/example databases.

The API and worker log only allowlisted operational metadata. The review pipeline and reviewer
routes do not log call, transcript, summary, or feedback content. Access logs are disabled. Request
headers, query strings, error details, database URLs, caller data, audio, and transcript content
cannot enter the application logger.

`make test-fixtures` uses only the local `colacci_test` database and local fixture adapters. It
writes `report.json`, accepted English and Spanish examples, and one rejected-output example to
`/tmp/colacci-law-fixtures/`; generated evidence is never written into the repository.

`make test-e2e` uses a disposable Compose project and database. It validates the report-first
flow, evidence focus, feedback persistence, role denial, failure history, playbook publication,
WCAG 2 A/AA and 2.1 A/AA automated checks, and content-free application logs. Evidence defaults
to `/tmp/colacci-law-slice2-evidence/` and may be redirected with `SLICE2_EVIDENCE_DIR`.

`make test-transcription-cli-offline` runs the injected CLI contract suite and the dedicated real
child-process harness with external networking disabled. It also imports one invented transcript
artifact through the existing review, report, evidence, and feedback contracts, repeats the import
to prove idempotency, and rejects invalid artifacts before database mutation. The normal API and
worker still construct no CLI client. The owner-gated Slice 3B live command remains a separate,
unchanged future verification boundary.

`make test-manual-upload` accepts only one browser-selected artifact and requires a generated-only
attestation. The server authorizes the authenticated demo principal before reading or allocating,
checks request and media boundaries, creates only opaque receipts and objects, deduplicates by
submission ID and content fingerprint, supports bounded retry and pre-processing cancellation,
and confirms temporary-media cleanup. Transcript-only input creates no media object. The command
proves stable failures, idempotency, report/call navigation, evidence focus, feedback persistence,
responsive layout, accessibility, content-free logs, and zero provider requests.

See [architecture](docs/architecture.md), [technology choices](docs/technology.md),
[configuration rules](docs/configuration.md), [adapter boundaries](docs/adapters.md), and the
[security documentation](docs/security/README.md).
