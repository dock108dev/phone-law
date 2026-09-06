# SSOT enforcement validation — September 6, 2026

The implementation is uncommitted on base `5a59ead`, preserving preceding error-handling,
security and CI changes. This record supersedes prior validation only for the current working
source; it is not exact-candidate, hosted, production or owner-acceptance proof.

## Changes exercised

- Route, validation, body and unexpected-error envelopes share `errors.py`.
- Settings and offline preflight use one endpoint classifier.
- Demo/test configuration rejects unsupported adapter selectors before service construction.
- Deleted the network SDK builder, live runner, Make target and obsolete linter exception.
- Retained the old factory only as an unconditional typed failure, tested even with all gates set.
- Added sixteen tests (twelve profile/configuration cases and four SSOT guards); changed the
  successful live-construction test into a rejection test and updated the safe-default assertion.

See [domain ownership and dispositions](ssot.md) for authoritative files, callers, retained
engineering paths and the schema/evidence-sensitive retirement follow-up.

## Execution

All application checks ran in separate Compose projects `colacci-law-ssot-proof` and
`colacci-law-ssot-browser` with private attempt-owned runtime directories and no published ports.
Pinned images were rebuilt against current source. The retained default demo was not restarted,
reconfigured or used as the validation database. Synthetic fixtures only; no provider requests.

| Command/check | Result |
| --- | --- |
| `make bootstrap` | PASS: pinned images, PostgreSQL initialization and migration |
| `make lint` | PASS: formatting, Ruff, Bandit, pin/schema/secret checks and ESLint |
| `make typecheck` | PASS: mypy (100 files) and TypeScript |
| `make test` | PASS: 310 Python unit tests, 82.34% coverage; 10 web tests |
| `make test-e2e` | PASS: seven browser journeys (3 + 1 + 3), log inspection and campaign cleanup |
| `make build` | PASS: TypeScript and production Vite build |
| `make test-integration` | PASS: 18 migration-backed integration tests |
| `docker compose up -d --wait api worker web` and `make smoke` | PASS: five readiness components |
| `scripts/test_transcription_contract.py` in a network-disabled container | PASS: 17 cases, 23 mock requests, zero external requests, live construction rejected, cleanup confirmed |
| Removed-symbol search | PASS: old live command/builder and duplicate endpoint validator occur only in removal documentation and regression guards |
| `git diff --check` | PASS |
| Hosted CI and owner acceptance | NOT RUN: no commit/push or owner review in this task |

The 206 existing Bandit annotation warnings remain. An initial standalone lint command used a
read-only cache path and was corrected to `/tmp`; the first Python run caught one test still
matching the retired error text. That assertion was updated, then the full gate passed. Initial
logs are retained rather than presented as successful evidence.

Evidence: `/tmp/colacci-law-ssot-evidence/` (`gates.log`, `python.log`, `media.log`, `browser.log`,
`cleanup.log`, and final source checksums). Browser evidence is under
`/tmp/colacci-law-ssot-browser-evidence/`. These local temporary files may be removed by the OS.
