# Error-handling maintenance validation — 2026-09-16

Started with clean HEAD `0a791cddeaeda10abc85a0f8010ce901c3d46b3c`, tree
`6b75423c56e5cf9ede425c07b0d3162ab48a29d3`. Results describe the uncommitted
working source, not a frozen candidate, owner acceptance or release qualification.

## Implemented findings

- **High — internal errors exposed as expected HTTP outcomes.** Review and
  operations routes caught all `ValueError`/`LookupError` exceptions. This included
  stored-model validation failures and programming lookup errors; some returned
  exception text. Explicit repository missing/conflict exception types now retain
  expected 404/409 behavior. Unexpected failures reach the existing sanitized 500
  and error-level diagnostics. No database schema or transaction behavior changed.
- **High — uncertain execution reported as zero requests.** An outcome persistence
  failure could escape a probe after dispatch and be reported as zero activity.
  Failed `run` now reports unknown requests and exits 2. An interrupted reservation
  write reports uncertain durable state, not a definite pre-reservation rejection.
- **High — cleanup prevented outcome recording.** Generated-media deletion errors
  previously skipped the outcome write. Cleanup now records an explicit failure,
  preserves the prior execution status/code, and attempts the outcome write.
  Execution, cleanup and evidence-write faults emit separate sanitized diagnostics.
  Unexpected faults and keyboard interruption remain fail-closed with no retry.

## Review scope and retained resilience

Reviewed repository exception/suppression searches across application routes,
frontend request/render handling, database transactions, media/import processing,
configuration, readiness, logging, host-only P1 tools, scripts and CI settings.
Read the current README, Desktop tracker, maintenance guide, observability ADR and
previous error-handling runbooks before editing. The application remains offline;
there is no production deployment or queue consumer to qualify.

Retained the existing sanitized HTTP boundary; typed media deletion failure;
classified fixture/structured-output rejection; bounded CLI timeout/cancellation
and no-retry controls; fail-closed journal/witness checks; explicit readiness 503s;
and web uncertain-save handling. Demo authentication audit remains best effort on
SQL failure while denial remains enforced. Raw SQL/process/request content stays
excluded from diagnostics. These are deliberate boundaries, not generic success
fallbacks. No new logging backend, scheduler or recovery service was introduced.

## Checks actually run

All executable checks used standalone disposable containers with `--network none`,
image `colacci-law-python-dependency-check:latest`, Python 3.14.7. Verification
mounted current source read-only at `/workspace`, set `PYTHONPATH=/workspace`,
`PYTHONDONTWRITEBYTECODE=1`, and put tool caches under container `/tmp`. Formatting
used a separate writable source mount for the explicitly edited files. No Compose
project, retained service, host credential or private campaign directory was mounted.

| Check | Result |
| --- | --- |
| `ruff check apps packages scripts tests` | Pass |
| `ruff format --check apps packages scripts tests` | Pass, 142 files |
| `mypy apps packages scripts` | Pass, 104 source files |
| Focused pytest command below | 115 passed, 2 skipped |
| `python scripts/verify_dependency_pins.py` | Pass |
| `python scripts/secret_scan.py` | Pass |
| Edited Markdown relative file links and `git diff --check` | Pass |

```sh
pytest -q tests/unit/test_repository_error_boundaries.py \
  tests/unit/test_p1_local_probe.py tests/unit/test_abend_handling.py \
  tests/unit/test_exception_boundaries.py tests/unit/test_database_model_hydration.py \
  tests/unit/test_local_operations_contracts.py tests/unit/test_review_contracts.py
```

The two skips exclude nonexistent month-conflict and configuration-not-found
outcomes from the parameterized matrix. Tests inject repository errors through
real HTTP middleware, assert repeated safe 500s and retained expected 4xx outcomes,
and use disposable invented campaign state for probe fault injection. Provider
execution, credentials, CLI process and tunnel are replaced with local test doubles.
Initial static validation found new exception naming and import-order issues;
these were repaired before the final passing checks.

## Boundaries and follow-up

No database integration, browser, full CI matrix, live smoke/provider request,
account access, packaging, signing, commit, push or release ran. The changed Python
components passed parsing/type checks; no frontend source changed or frontend build
was run. Process-kill, real filesystem crash and macOS sandbox campaigns were not
rerun; injected failures do not establish those platform guarantees.

Retained preparation and owner acceptance apply to their recorded identities.
Changes under `packages` and `scripts` alter the probe implementation identity.
The Desktop tracker now requires bounded source/preparation reconciliation before
fresh owner-local entry; no manifest, sample, ledger or approval was updated here.
Production alert routing, persistent metrics and stale-job/crash recovery remain
separate operational work. See [current failure behavior](error-handling.md).
