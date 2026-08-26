# Continuous integration

GitHub Actions runs the `CI` workflow for pull requests targeting `main` and pushes to `main`.
All jobs use read-only repository permissions, cancel superseded runs, execute untrusted pull
request code without secrets, and time out rather than consuming a runner indefinitely.

Expected pull-request status checks:

- `Quality` validates Compose, builds the pinned API and web images, then runs formatting,
  linting, type checking, unit/security tests, the production web build, and dependency audits.
- `Integration` bootstraps PostgreSQL, runs the migration-backed integration suite, starts
  the application, and verifies API, worker, web, dashboard, database, and migration readiness.
- `Browser` runs the disposable synthetic reviewer, manual-upload, and operations journeys.
  Its sanitized evidence is retained for seven days to diagnose failures.

Third-party actions are pinned to immutable commits with release comments. Dependabot groups
weekly updates for Python, npm, Compose images, runtime images, and GitHub Actions. Provider-facing
tests, release operations, deployment, and owner acceptance are intentionally excluded from pull
request CI because they require separate authorization or external state.

To reproduce the required checks locally, start Docker and run:

```bash
docker compose config --quiet
docker compose build api web
make lint typecheck test build audit
make bootstrap
make test-integration
docker compose up -d --wait api worker web
make smoke
make test-e2e
make stop
```

Hosted jobs build from their checked-out source before executing application gates. The separate
local owner-demo candidate uses `make test-demo-release`, which additionally labels and verifies
the exact commit, Git tree, declared runtime contract, image identities, and actual container
runtimes before deterministic seeding.

GitHub-hosted runner behavior, branch-protection requirements, repository rulesets, and GitHub's
default CodeQL setup cannot be fully reproduced locally. Repository settings are owner-managed and
are not changed by the workflow.
