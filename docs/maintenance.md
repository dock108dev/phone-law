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

`apps/web/src/App.tsx` contains routing and principal state. Eight page modules under `pages/`
contain their own view state; `shared.tsx` contains common presentation. API access remains in
`api.ts`. Provider/CLI process experiments are fully retired.

The remaining source/test files over roughly 500 lines are listed below. Counts are a review
snapshot, not a size limit. Splitting transactional methods or shared page state solely to hit a
line count would obscure behavior.

| File | Lines | Reason retained |
|---|---:|---|
| `packages/database/local_operations.py` | 1111 | Retention, deletion and recovery share transaction and failure-plan invariants |
| `packages/database/review_experience.py` | 1019 | Report, feedback and playbook operations share immutable-record and audit invariants |
| `packages/manual_upload/service.py` | 634 | One receipt lifecycle spans validation, retry, cancellation and cleanup |
| `tests/integration/test_manual_upload_full_loop.py` | 580 | Sequential lifecycle assertions share database setup and exact state transitions |
| `packages/review/demo_month.py` | 530 | Deterministic v1 recipe and v2 authored-entry loading share validation; both have explicit callers and tests |
| `packages/contracts/review.py` | 525 | One related strict model/schema family with cross-record validators |

Historical migration payloads, tables and serialized provenance are retained as read compatibility,
not executable provider code. Integration tests cover migration replay without losing invented
historical metadata. No provider-tooling retirement follow-up remains.

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
