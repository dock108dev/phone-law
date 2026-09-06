# Maintainer guide

## Where changes belong

- Add or change HTTP routes under `apps/api/colacci_api`; keep business and persistence behavior in
  the corresponding `packages` module.
- Change demo permissions only in `packages/authorization/demo_policy.py`. Capability responses,
  route enforcement, and repository defense checks must derive from that policy.
- Change environment behavior only in `packages/config/settings.py` and update `.env.example`,
  `docker-compose.yml`, `docs/configuration.md`, and settings tests together.
- Change strict contracts in `packages/contracts`, regenerate schemas with
  `make generate-contract-schemas`, and run `make lint` to verify synchronization.
- Change database shape through an append-only Alembic migration. Do not rewrite historical
  migration payloads to match current constants.
- Keep browser requests in `apps/web/src/api.ts`; page code should not construct a second error or
  identity-header policy.
- Put operator procedures in runbooks and durable architecture rationale in ADRs. Current roadmap
  status never belongs in repository documentation.

## Module boundaries and large files

CLI process execution lives in `packages/transcription/cli_process.py` (179 lines): executable
allowlists, child environments, output limits, cancellation and process-group cleanup stay together.
`cli_local.py` (446 lines) owns capability discovery, authorization and response adaptation. The
public `packages.transcription` imports remain stable. Existing fake-process security checks
exercise the extracted code without provider access.

The remaining source/test files over roughly 500 lines are listed below. Counts are a review
snapshot, not a size limit. Splitting transactional methods or shared page state solely to hit a
line count would obscure behavior.

| File | Lines | Reason retained |
|---|---:|---|
| `apps/web/src/App.tsx` | 1245 | Shared navigation, role switching and review state; page extraction needs dedicated visual/state regression review |
| `packages/database/local_operations.py` | 1111 | Retention, deletion and recovery share transaction and failure-plan invariants |
| `packages/database/review_experience.py` | 1019 | Report, feedback and playbook operations share immutable-record and audit invariants |
| `packages/manual_upload/service.py` | 634 | One receipt lifecycle spans validation, retry, cancellation and cleanup |
| `tests/integration/test_manual_upload_full_loop.py` | 580 | Sequential lifecycle assertions share database setup and exact state transitions |
| `packages/review/demo_month.py` | 530 | Deterministic v1 recipe and v2 authored-entry loading share validation; both have explicit callers and tests |
| `packages/contracts/review.py` | 524 | One related strict model/schema family with cross-record validators |
| `scripts/test_transcription_contract.py` | 505 | One network-blocked provider-contract campaign produces a single evidence result |

Historical migration payloads and offline provider metadata are retained deliberately; the
[SSOT inventory](ssot.md#bounded-follow-up) owns their retirement scope. They are not examples of
current production capability. No unused TODO or commented-out implementation block was found in
the source/script scan.

## Change validation

For ordinary source changes, run `make lint`, `make typecheck`, `make test`, and the affected
integration or browser gate. Run `make smoke` after runtime, configuration, route, container, or
migration changes. `make audit` is a separate online advisory check and does not replace pinned
offline validation.

Do not commit generated evidence, temporary media, credentials, local databases, coverage output,
or environment files. Preserve the synthetic-only boundary. Clean up only the project and runtime directories owned
by the validation attempt; leave any retained demo stack running.


Schema generation uses the selected Compose API image and the invoking user ID, with a writable
source mount. Run `make bootstrap` (or build that project’s API image) before
`make generate-contract-schemas`; the command does not require a default-image alias or database.
Generated schemas must pass `make lint` without unrelated schema changes.
