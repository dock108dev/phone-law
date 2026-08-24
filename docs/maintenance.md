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

## Large cohesive files retained

These files exceed roughly 500 lines after review. They remain intact because the methods share
state, transactional invariants, or one generated contract family; splitting them into mixins or
thin forwarding files would obscure the supported execution path.

| File | Reason retained |
|---|---|
| `apps/web/src/App.tsx` | One small application with tightly coupled page state and shared role switching; page extraction is a separate UI refactor requiring dedicated visual review |
| `packages/database/local_operations.py` | One transactional retention/deletion/recovery boundary with injected clock and failure plan |
| `packages/database/review_experience.py` | One report, feedback, failure, and playbook repository over shared immutable records |
| `packages/manual_upload/service.py` | One receipt lifecycle coordinating validation, processing, retry, cancellation, and cleanup |
| `packages/transcription/cli_local.py` | One hardened subprocess/capability boundary whose security invariants span discovery through cleanup |
| `packages/contracts/review.py` | One generated review-contract family; schemas and validators are easier to audit together |
| `packages/transcription/openai_adapter.py` | One response conversion, retry, and gated-construction boundary |
| `tests/integration/test_manual_upload_full_loop.py` | End-to-end lifecycle assertions share expensive database fixtures and exact state sequences |
| `scripts/test_transcription_contract.py` | Standalone network-blocked contract harness with a single evidence result |

Revisit a split only when a new independent caller or responsibility appears. Any extraction must
preserve exact state outcomes, transaction boundaries, cleanup, and content-free evidence.

## Change validation

For ordinary source changes, run `make lint`, `make typecheck`, `make test`, and the affected
integration or browser gate. Run `make smoke` after runtime, configuration, route, container, or
migration changes. `make audit` is a separate online advisory check and does not replace pinned
offline validation.

Do not commit generated evidence, temporary media, credentials, local databases, coverage output,
or environment files. Preserve the synthetic-only boundary and stop the default stack after
isolated acceptance work unless an operator explicitly needs it running.
