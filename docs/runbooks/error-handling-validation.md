# Error-handling implementation validation — 2026-09-06

Historical record: provider/CLI experiments are now retired. Use [current documentation](../README.md) for supported commands.

Base: `5a59ead` (clean at entry). Changes remain uncommitted. These results cover
the working source, not a frozen release or an owner-accepted candidate.
Logs are retained at `/tmp/colacci-law-abend-evidence/` with restrictive permissions.

## Results

| Checks actually run | Result / evidence log |
| --- | --- |
| `ruff format --check apps packages scripts tests`; `ruff check apps packages scripts tests` | Pass; `python-final.log` |
| `bandit -q -c pyproject.toml -r apps packages scripts` | Pass; 206 annotation warnings identical to untouched base, `warning-comparison.txt` |
| `python scripts/verify_dependency_pins.py`; `python scripts/generate_contract_schemas.py --check`; `python scripts/secret_scan.py` | Pass; pins verified, 25 schemas, no secret findings |
| `mypy apps packages scripts` | Pass, 99 source files |
| `pytest -m "not integration" --cov --cov-report=term-missing` | 272 passed, 18 deselected; 81.96% coverage |
| `npm run lint`; `npm run typecheck`; `npm test -- --run`; `npm run build` | Pass, 10 tests; `web.log` |
| `pytest -m integration` | 18 passed, 272 deselected; `integration-final.log` |
| `python scripts/evaluate_fixtures.py` | 12 scenarios passed; `integration-final.log` |
| `make test-e2e` with the overrides below | 7 journeys passed; log privacy inspection passed; owned stack/runtime cleanup passed; `e2e-verified.log` |
| `python scripts/test_audio_boundary.py` | 6 accepted, 5 rejected, 11 deletions, zero remaining; first line of `media-contract-verified.log` |
| `python scripts/test_transcription_contract.py` | 17 mocked cases, 23 mock requests, zero external requests, cleanup confirmed; `transcription-contract-final.log` |
| `python scripts/test_cli_process_security.py` | 8 cases, network disabled, cleanup confirmed; same log |
| `python scripts/smoke.py` | All 5 components pass after restoring the retained demo; `smoke-final.log` |
| `pip-audit --require-hashes -r requirements.lock`; `npm audit --audit-level=high` | No known vulnerabilities; `python-audit.log`, `web-audit.log` |
| `git diff --check` | Pass |

Python checks used the pinned `colacci-law-api:latest` runtime (Python 3.14.7,
Ruff 0.16.5, mypy 2.3.1, pytest 9.1.1, OpenAI 3.5.0), with the working source
mounted read-only at `/workspace`, `PYTHONPATH=/workspace`, and temporary
Ruff/mypy/coverage output paths. Non-database checks used `--network none`.
Web checks used the freshly built `colacci-law-abend-e2e-web` image with current
`apps/web/src` mounted read-only. Dependency audit containers alone used network
access to vulnerability services; no product provider calls occurred.

Integration used a separately created internal Docker network and PostgreSQL
17.6 container, database `colacci_test`, synthetic generated upload assets and
`alembic upgrade head`. It did not reset or migrate the retained demo database.
Media was generated with the host's offline macOS voices using
`COLACCI_SYNTHETIC_ROOT=/tmp/colacci-law-abend-media`, then mounted at the
harness-required `/tmp/colacci-law-slice3a` inside network-disabled containers.
Assets were regenerated between the audio and transcription harnesses because
the audio harness intentionally deletes them.

Final browser command:

```bash
COLACCI_E2E_PROJECT=colacci-law-abend-verified \
SLICE4_RUNTIME_ROOT=/tmp/colacci-law-abend-verified-runtime \
SLICE4_EVIDENCE_DIR=/tmp/colacci-law-abend-verified-evidence \
make test-e2e
```

## Initial failures and recovery

All failed attempts were retained rather than counted as passes:

- Static checks found import ordering, a worker override annotation and an
  unnecessary TypeScript assertion; these were corrected before final checks.
- Source scanning correctly exposed binary `.DS_Store` as unreadable. That macOS
  metadata file is now explicitly outside the source scan. The older unit test
  asserting that unreadable source produces no findings was updated to require a
  failure finding.
- Initial browser journeys passed, but final cleanup rejected a concurrent web
  quality container that inherited the browser image's Compose project label.
  That container finished and was removed; later checks used distinct labels.
  Fresh browser campaigns then completed including cleanup.
- An initial media invocation ran macOS generation inside Linux, then another
  used the wrong mount target. The corrected media harness passed and removed
  its inputs, so transcription needed fresh assets. The final transcription and
  child-process security harnesses passed independently.
- A smoke probe overlapped the disposable browser harness's intentional schema
  downgrade and correctly returned 503. Final smoke passed on a stable stack.
- The first `docker compose run --no-deps api` runtime inspection recreated the
  retained demo's application network and lost service aliases. Aliases were
  restored; the API process required restart to clear a stalled connection.
  API, worker, web and database were all healthy afterward. No retained data was
  reset. Future one-off checks should use explicitly labelled standalone
  containers and isolated networks instead of touching that Compose project.

## Not run / separate qualification

Hosted CI/CodeQL, full exact-candidate release/acceptance campaigns, owner review,
and live provider tests were not run. The candidate gates require a fresh clean
owner-managed Git handoff; provider and production phases require separate
explicit authorization. The seven browser journeys include the manual-upload
and Operations flows, and the full database suite includes their persistence and
failure tests; this is not a claim that every historical evidence wrapper ran.
Production alert routing and stale-processing/crash recovery remain separate
work described in the incident runbook.
