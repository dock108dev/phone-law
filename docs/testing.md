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
the demo database. Stop the default stack with `make stop` when finished.

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
| `make test-transcription-contract` | Provider-response conversion, retry classification, or safe transcription metadata |
| `make test-transcription-cli-offline` | Local CLI capability/process isolation or transcript-only import |
| `make test-manual-upload` | Upload request parsing, receipt lifecycle, temporary objects, or upload UI |
| `make test-local-operations` | Role policy, configuration versions, retention/deletion, restore drill, or operations UI |
| `make test-demo-month` | Month generation, daily/month reconciliation, or month-history UI |
| `make test-local-acceptance` | Combined acceptance on clean historical slice branches or a verified exact `main` candidate |

`make transcription-live-preflight` and `make test-transcription-live` are not routine tests. The
first is a network-disabled owner-authorization preflight; the second is a separately authorized
generated-audio provider verification. Never use the live command as a fallback or CI gate.

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

Evidence, screenshots, logs, generated media, coverage files, and local databases are not source
artifacts and must not be committed. CI retains only sanitized browser evidence or failure logs for
seven days. See [Continuous integration](continuous-integration.md) for the exact GitHub checks.

## Choosing the minimum gate

Documentation-only changes still run `make lint` because it includes schema, secret, and web lint
checks. Ordinary source changes run lint, type checking, unit tests, and the affected focused gate.
Changes to routes, runtime settings, containers, or migrations also run integration and smoke.
Cross-cutting browser behavior runs `make test-e2e`. Dependency changes additionally run the
online `make audit`.
