# Continuous integration

GitHub Actions runs the `CI` workflow for pull requests targeting `main` and pushes to `main`.
All jobs use read-only repository permissions, cancel superseded runs, execute untrusted pull
request code without secrets, and time out rather than consuming a runner indefinitely.

Expected pull-request status checks:

- `Dependencies` checks declaration/lock agreement before any application build, then installs
  the exact npm graph in both web and Playwright images with strict peer checking and `npm ls`.
  Its logs are retained on failure. All three application jobs require this check to pass.
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

## Dependency update procedure

The September 15 failure was TypeScript 7.0.2 paired with typescript-eslint 8.70.0,
whose peer range is `>=4.8.4 <6.1.0`. Keep TypeScript at 6.0.3 until a coordinated
compiler/linter upgrade is supported. Dependabot excludes TypeScript >=6.1.0 and
npm major updates; minor/patch updates for the other npm packages continue weekly.
Revisit the ceiling when upgrading typescript-eslint. Do not use `--force` or
`--legacy-peer-deps` to hide incompatibilities.

Node, Python and Playwright runtime images, plus `@playwright/test`, require manual
coordinated updates because Dependabot's separate Docker/npm jobs cannot update
all their companion declarations. Review these weekly alongside the automated PRs:

- Node image tag and `.nvmrc` together; check npm's supported Node range.
- Python image, `.python-version`, and `pyproject.toml` together.
- Playwright image and `@playwright/test` together; regenerate the npm lock.
- npm version in `packageManager`, `engines.npm`, and both Dockerfiles together.
- For each Python requirements PR, regenerate `requirements.txt` with
  `pip-compile --generate-hashes --output-file=requirements.txt requirements.in`
  under the pinned Python runtime before merging when repairing a lock manually.
  The canonical pip-compile pair is `requirements.in` and `requirements.txt`.
  Dependabot recognizes the `.txt` output and can update the pair together.
  An input-only change remains incomplete; the early gate rejects it.

Regenerate the npm lock with the Dockerfile's pinned Node/npm versions, then run
`python scripts/verify_dependency_pins.py` and build both Dockerfiles. Each has a
`dependencies` target for an install-only check. Full builds retain the runtime
candidate labels and non-root users. Run lint, typecheck, tests, build and audits
against the resulting candidate before merging.

Configure branch protection to require `Dependencies`, `Quality`, `Integration`,
and `Browser` on `main`. Source checks alone cannot prevent a failed PR from being
merged. A read-only check on September 15 found that `main` is still unprotected;
this repair does not change repository settings or establish hosted CI success.

### Local repair verification — September 15, 2026

Working-tree repair based on `a6ed03d`:

- Fresh, uncached web and Playwright image builds passed; Python image built with
  the regenerated hash-locked Ruff 0.16.7 dependency.
- Dependency declaration checks and all seven existing drift regression tests passed.
- Web lint, typecheck, 11 unit tests, production build, and npm audit passed
  (zero reported vulnerabilities).
- The new dependency target rejected the original merged TypeScript 7.0.2
  manifest/lock with `ERESOLVE`, reproducing the reported failure.
- Workflow lint, Compose configuration, and diff whitespace checks passed.

This is local dependency-repair evidence, not a full integration/browser journey
run, hosted CI result, new owner acceptance, or production qualification.

### Python lock discovery repair — September 15, 2026

Dependabot updated Alembic to 1.20.0 in `requirements.in` while the old
`requirements.lock` retained 1.19.2. Dependabot's Python fetcher discovers `.in`
and `.txt` files, and its pip-compile matcher requires a `.txt` output. Renamed
the canonical hash lock to `requirements.txt` and updated Docker, audits, pin
checks, tests, and the probe source-identity calculation. Historical validation
reports retain the old filename. No duplicate lock is maintained.

Source: [Dependabot pip-compile matcher](https://github.com/dependabot/dependabot-core/blob/main/python/lib/dependabot/python/pip_compile_file_matcher.rb).
This removes the discovery mismatch; a future hosted Dependabot run is still
needed to confirm its complete update behavior on this repository.

Local verification: the Python image built with hash enforcement, installed
Alembic 1.20.0, and passed `pip check`. Full lint and all 400 unit tests passed.
The unit suite also exposed a stale Node 26.8.1 test literal; the assertion now
compares against `.nvmrc`. No hosted Dependabot update, migration-backed
integration run, provider call, or new owner acceptance is claimed.
