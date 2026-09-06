# Testing and validation

Tests use deterministic invented data. Routine gates do not call OpenAI, telephony, email, cloud
storage, identity, or notification services. Docker and Compose run project dependencies; host
`python3` is used only by deterministic fixture/evidence helpers.

## Core engineer gate

| Command | What it verifies | External network |
|---|---|---|
| `make lint` | Ruff format/check, Bandit, exact pins, generated schemas, repository secret scan, ESLint | No after images exist |
| `make typecheck` | Strict mypy and TypeScript checks | No |
| `make test` | Python unit/security suite with 80% coverage gate and Vitest web tests | No |
| `make build` | TypeScript validation and production Vite bundle | No |
| `make test-integration` | Alembic downgrade/upgrade behavior and PostgreSQL repositories | No beyond the local Compose network |
| `make smoke` | API, worker, web, dashboard, database, and exact migration readiness | No beyond the local Compose network |
| `make test-e2e` | Reviewer, manual-upload, and operations Playwright journeys plus safe-log inspection | No beyond the local Compose network |
| `make audit` | Current Python and npm vulnerability advisories | Yes; public package/advisory registries |

Run `make bootstrap` before the core gate on a new checkout. It builds pinned images with hashed
Python dependencies and `npm ci`, starts PostgreSQL, initializes the test database, and migrates
the demo database. For a retained demo, use the separate-project commands in
[CI reproduction](continuous-integration.md); clean up only that validation project.

`make test-demo-release` is stricter than ordinary local gates. It requires a clean checkout,
builds API, worker, web, and browser images with the exact candidate commit, Git tree, and runtime
contract labels, verifies those labels and the runtimes inside each image, writes private sanitized
image evidence, and only then begins deterministic seeding. Existing `latest` tags are never
accepted as candidate evidence without that rebuild and verification.

## Focused gates

| Command | Use when changing |
|---|---|
| `make test-fixtures` | Fixture analysis, report classification, evidence validation, or reconciliation |
| `make test-audio` | Media signature inspection, normalization, object cleanup, or metadata |
| `make test-manual-upload` | Upload request parsing, receipt lifecycle, temporary objects, or upload UI |
| `make test-local-operations` | Role policy, configuration versions, retention/deletion, restore drill, or operations UI |
| `make test-demo-month` | Month generation, daily/month reconciliation, or month-history UI |
| `make test-local-acceptance` | Combined acceptance on clean historical slice branches or a verified exact `main` candidate |

`make test-local-acceptance` is not a general current-branch gate. Its script requires a clean
checkout descended from its accepted source and either an allowlisted historical branch or `main`.
On `main`, the separately authorized candidate campaign must first build exact candidate images;
the acceptance script independently rechecks their commit, tree, runtime-contract labels, image
identities, and actual runtimes before retagging them into its disposable proof stack.

## Isolation and outputs

Unit tests run in read-only application images. Integration tests use the local `colacci_test`
database. Browser and focused acceptance scripts create named disposable Compose projects,
internal or network-disabled test paths, generated non-human inputs, and evidence beneath
project-specific `/tmp/colacci-law-*` directories. They inspect application logs before cleanup.

`make test-fixtures` requires a `_test` database, upgrades it to the current revision, and
truncates its fixture/review records before evaluation. The legacy report field
`network_used=false` denotes no external provider use; the evaluator still connects to local
PostgreSQL over the Compose network. It is destructive to that test database;
use the dedicated project, image, network and report-root settings from local development.

Evidence, screenshots, logs, generated media, coverage files, and local databases are not source
artifacts and must not be committed. CI retains the Quality log, browser evidence and failure service diagnostics for
seven days. See [Continuous integration](continuous-integration.md) for the exact GitHub checks.

## Choosing the minimum gate

Documentation-only changes still run `make lint` because it includes schema, secret, and web lint
checks. Ordinary source changes run lint, type checking, unit tests, and the affected focused gate.
Changes to routes, runtime settings, containers, or migrations also run integration and smoke.
Cross-cutting browser behavior runs `make test-e2e`. Dependency changes additionally run the
online `make audit`.


## Transcript fixture verification

`scripts/verify_transcript_import.py` is an engineering harness for the fixed invented fixture,
not a general importer. It checks invalid-input rollback and idempotency, builds a report, adds
synthetic reviewer feedback and writes private evidence. It refuses a database without the
`_test` suffix or with any review records before modifying fixtures or persisted state.

Use a fresh disposable Compose project from [CI reproduction](continuous-integration.md), run
`make bootstrap`, and run this **before** the integration suite populates the test database:

```bash
docker compose run --rm --no-deps -e APP_PROFILE=test \
  -e DATABASE_URL=postgresql+psycopg://colacci_demo:local-demo-only-password@db:5432/colacci_test \
  api alembic upgrade head
docker compose run --rm --no-deps \
  -e DATABASE_URL=postgresql+psycopg://colacci_demo:local-demo-only-password@db:5432/colacci_test \
  -v "$PWD/fixtures/transcript-only:/workspace/fixtures/transcript-only:ro" \
  api python scripts/verify_transcript_import.py
```

Evidence remains in the ephemeral container unless a fresh private host evidence directory is
mounted at `/tmp/colacci-law-slice3c`. Do not reuse a retained runtime/evidence directory. For
ordinary product input, use the authenticated manual-upload page, which validates the same
artifact contract without running test assertions or adding test feedback.

## Validation boundaries

The normal setup, core tests and browser journeys can run with Docker locally. Media generation
uses macOS `say` and `afconvert`; run `make test-audio` on a Mac with the required voices, using a
fresh `COLACCI_SYNTHETIC_ROOT`. Builds, audits and workflow linting fetch public dependencies.
`make test-demo-release` and `make test-local-acceptance` require a clean, identity-qualified
candidate and are separate from this working-tree check. Hosted action execution and artifact
uploads require a GitHub run. No production deployment workflow exists; see
[deployment boundaries](runbooks/staging-production-safety.md).
