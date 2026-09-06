# Continuous integration

GitHub Actions runs the `CI` workflow for pull requests targeting `main` and pushes to `main`.
All jobs use read-only repository permissions, cancel superseded runs, execute untrusted pull
request code without secrets, and time out rather than consuming a runner indefinitely.

Expected pull-request status checks:

- `Quality` validates workflows with checksum-pinned actionlint and validates Compose,
  builds the pinned API and web images, then runs formatting,
  linting, type checking, unit/security tests, the production web build, and dependency audits.
  Its command log (including coverage) is retained for seven days, even on failure.
- `Integration` bootstraps PostgreSQL, runs the migration-backed integration suite, starts
  the application, and verifies API, worker, web, dashboard, database, and migration readiness.
- `Browser` runs the disposable synthetic reviewer, manual-upload, and operations journeys.
  Its sanitized evidence is retained for seven days to diagnose failures.

Third-party actions are pinned to immutable commits with release comments. Dependabot groups
weekly updates for Python, npm, Compose images, runtime images, and GitHub Actions. Provider-facing
tests, release operations, deployment, and owner acceptance are intentionally excluded from pull
request CI because they require separate authorization or external state.

The dependency gate rejects disagreement between runtime declarations, direct dependencies and
lockfiles, npm versions, and the Playwright package/image pair. Update related declarations
together when accepting dependency updates. Hosted runners install the hash-locked Python graph
and use `npm ci` inside images; no external dependency/build cache is restored.

To reproduce the checks locally, start Docker and use a disposable source copy containing all
intended changes. Run from that copy with a separate Compose project and runtime directory:

```bash
./scripts/lint_workflows.sh
export COMPOSE_PROJECT_NAME=colacci-law-ci-local
export COMPOSE_FILE="$PWD/docker-compose.yml:$PWD/infrastructure/local/slice5a-compose.yml"
export SLICE4_RUNTIME_ROOT=/tmp/colacci-law-ci-local-runtime
docker compose config --quiet
docker compose build --no-cache api web
make lint typecheck test build audit
make bootstrap
make test-integration
docker compose up -d --wait api worker web
make smoke
docker compose down --volumes --remove-orphans
unset COMPOSE_PROJECT_NAME COMPOSE_FILE SLICE4_RUNTIME_ROOT
COLACCI_E2E_PROJECT=colacci-law-ci-local-browser \
  SLICE4_RUNTIME_ROOT=/tmp/colacci-law-ci-local-browser-runtime make test-e2e
```

These project/runtime names must be unused by other work. The override removes published ports;
smoke checks execute inside the containers. Clean up only these disposable resources if a command
fails. Workflow linting downloads an official, SHA-256-verified actionlint release and also invokes
ShellCheck when installed. Network access to release, image and package registries is required.

Hosted jobs build from their checked-out source before executing application gates. The separate
local owner-demo candidate uses `make test-demo-release`, which additionally labels and verifies
the exact commit, Git tree, declared runtime contract, image identities, and actual container
runtimes before deterministic seeding.

GitHub-hosted runner behavior, branch-protection requirements, repository rulesets, and GitHub's
default CodeQL setup cannot be fully reproduced locally. Repository settings are owner-managed and
are not changed by the workflow.

The read-only September 6, 2026 inspection found no branch protection or rulesets. GitHub default
CodeQL was configured for Actions, Python and JavaScript/TypeScript; its additional checks are
`Analyze (actions)`, `Analyze (python)` and `Analyze (javascript-typescript)`. These repository
settings may change independently of source. See [CI validation](ci-validation.md) for the
working-tree evidence and the distinction from prior hosted results.
