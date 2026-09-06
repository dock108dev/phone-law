# CI readiness validation — September 6, 2026

Historical record: provider/CLI experiments are now retired. Use [current documentation](README.md) for supported commands.

Expected pull-request result: **ALL CHECKS PASSING**, based on local execution and read-only
GitHub inspection. This is an uncommitted implementation handoff on base
`5a59ead1b4b5c4bdeb0b44eafdda6ffc9a9a34fa`, including the preceding error-handling and security
changes. It is not hosted proof for the changed source, candidate qualification or owner acceptance.

## Local execution

Copied tracked and intended non-ignored untracked files into `/tmp/colacci-law-ci-source`, excluding
Git metadata and ignored caches. API/web images were built with `--no-cache`; Python installation
used the hash-locked requirements and JavaScript used `npm ci`. Linux ARM containers ran on
macOS Docker Desktop. Projects `colacci-law-ci-proof` and `colacci-law-ci-browser`, separate runtime
directories and the port-free `slice5a-compose.yml` override isolated validation from the retained
demo. No default-project service was restarted or reconfigured during this CI review.

| Validation | Result | Evidence |
| --- | --- | --- |
| Workflow syntax/expressions | PASS | `./scripts/lint_workflows.sh`: actionlint 1.7.12, verified archive checksum, both working source and disposable copy |
| Shell syntax | PASS | `bash -n scripts/lint_workflows.sh scripts/bootstrap.sh` |
| Dependabot | PASS | Ruby YAML parse, five target directories exist; ecosystem/group/schedule configuration inspected |
| Compose and clean installs | PASS | `docker compose config --quiet`; `docker compose build --no-cache api web` |
| Formatting/lint/security/static contracts | PASS | `make lint`: Ruff, Bandit, dependency pins, generated schemas, secret scan, ESLint |
| Types | PASS | `make typecheck`: mypy (100 source files), TypeScript |
| Unit tests and coverage | PASS | `make test`: 294 Python tests, 82.23% coverage (80% minimum), 10 web tests |
| Production web build | PASS | `make build`: TypeScript and Vite |
| Dependency audits | PASS | `make audit`: no known Python or npm vulnerabilities |
| Database integration | PASS | `make bootstrap`, `make test-integration`: 18 tests |
| Service readiness | PASS | `docker compose up -d --wait api worker web`, `make smoke`: five components pass |
| Browser campaign | PASS | `make test-e2e`: seven journeys in groups of 3, 1 and 3; campaign cleanup succeeded |
| Current changed source on GitHub | NOT RUN | No commit or push authorized |
| ShellCheck integration | NOT RUN | ShellCheck absent locally; actionlint enables it automatically when available on the hosted runner |

The 206 existing Bandit annotation warnings remain; Bandit exits successfully. Logs are under
`/tmp/colacci-law-ci-evidence/`: `install.log`, `quality.log`, `integration.log`, `browser.log`, and
`actionlint-snapshot.log`. Browser artifacts are under `/tmp/colacci-law-ci-browser-evidence/`.
Temporary evidence is local and may be removed by the operating system. Final documentation-only
edits follow the executable test run; the source manifest records the delivered file identities.

## Read-only hosted inspection

- [CI run 34048390909](https://github.com/dock108dev/phone-law/actions/runs/34048390909) on base
  `5a59ead`: `Quality`, `Integration`, `Browser` succeeded.
- [CodeQL run 34048390537](https://github.com/dock108dev/phone-law/actions/runs/34048390537):
  `Analyze (actions)`, `Analyze (python)`, `Analyze (javascript-typescript)` succeeded.
- GitHub default CodeQL setup is configured for those languages with its default query suite.
- Main branch protection returned `404 Branch not protected`; repository rulesets returned `[]`.
  There are currently no enforced required checks. Enabling enforcement remains an owner settings
  decision; it is not necessary for the configured jobs to run.
- Checkout, setup-python and upload-artifact immutable commits matched their annotated release
  versions. PR/main triggers, read-only permissions, credential-free checkout, stable job names,
  cancellation, timeouts, script paths, action inputs and artifact paths were inspected.
- An older failed dependency-update run had an npm peer-resolution error; later PR and current
  main runs passed. The current locked graph also installed cleanly in this review.

## Changes and limits

Added checksum-pinned workflow linting, seven regression cases for dependency/runtime declaration
agreement, retained Quality logs and explicit missing-artifact warnings. Bash pipeline failure
propagation keeps a failing quality command from being hidden by `tee`. Aligned stale `.nvmrc`
with the existing Node container and corrected the runtime documentation. Bootstrap now respects
the configured disposable runtime directory.

No new runtime matrix or redundant application job was added: the project declares exact runtime
versions and CI targets Ubuntu containers. Local success does not prove GitHub's AMD64 runner,
action execution, artifact upload, cancellation or managed CodeQL behavior for these edits.
Registries, GitHub releases and vulnerability databases must remain reachable. Container tags
remain patch-pinned rather than digest-pinned, as documented in the existing technology policy.

No credentials, repository settings, release/publishing operations or provider integrations were
changed. Include all intended new files, particularly the workflow lint script and regression
tests, when preparing the eventual commit. Owner verdict remains **REVISE DEMO**.
