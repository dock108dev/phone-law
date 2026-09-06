# Current implementation sources of truth

This inventory describes the supported local synthetic system at the current repository head.
The Desktop roadmap remains the sole planning source of truth; this document identifies runtime
and policy ownership only.

## Authoritative domains

Domain: routing
SSOT module/file: `apps/api/colacci_api/app.py`
Why this is authoritative: `create_app()` constructs the only FastAPI application and includes
the review, upload, and operations routers.
Known callers: `apps/api/colacci_api/main.py`, API unit tests, browser and smoke harnesses.

Domain: configuration
SSOT module/file: `packages/config/settings.py`
Why this is authoritative: API, worker, migrations, scripts, and probes all instantiate the same
typed fail-closed settings model.
Known callers: API and worker entry points, Alembic, seed/evidence scripts, transcription commands.

Domain: demo authentication
SSOT module/file: `apps/api/colacci_api/demo_auth.py`
Why this is authoritative: it alone maps allowlisted synthetic principal IDs to server-resolved
roles and rejects the demo identity mechanism outside demo/test.
Known callers: every `/api` router through FastAPI dependency injection.

Domain: demo authorization
SSOT module/file: `packages/authorization/demo_policy.py`
Why this is authoritative: its immutable role-permission matrix drives route enforcement, upload
capabilities, operations presentation, and repository defense checks.
Known callers: review, upload, and operations routes; local operations persistence.

Domain: API error envelope
SSOT module/file: `apps/api/colacci_api/errors.py`
Why this is authoritative: route exceptions, middleware rejections and sanitized 422/500 responses use its error and correlation
shape.
Known callers: demo authentication, all three API routers, application and body-limit middleware.

Domain: browser API access
SSOT module/file: `apps/web/src/api.ts`
Why this is authoritative: browser requests, demo identity headers, response parsing, and safe
client errors all pass through `apiRequest`.
Known callers: page modules under `apps/web/src/pages/`.

Domain: fixture ingestion and retry
SSOT module/file: `packages/review/pipeline.py`
Why this is authoritative: `FixturePipeline` owns the processing state machine sequence and
persists attempts through `ReviewRepository`.
Known callers: demo/month seeders, fixture evaluator, retry route, integration tests.

Domain: invented transcript ingestion
SSOT module/file: `packages/review/transcript_import.py`
Why this is authoritative: it performs whole-artifact validation, deterministic identity,
idempotent persistence, and fixture analysis for the supported transcript-only contract.
Known callers: manual-upload service and the explicit offline import command.

Domain: interactive manual upload
SSOT module/file: `packages/manual_upload/service.py`
Why this is authoritative: it owns receipt lifecycle, generated-media allowlisting, processing,
retry/cancel behavior, and cleanup while delegating accepted review records to existing domain
repositories.
Known callers: `apps/api/colacci_api/upload_routes.py` and focused integration tests.

Domain: persistence
SSOT module/file: bounded repositories under `packages/database`
Why this is authoritative: `ReviewRepository` owns processing writes,
`ReviewExperienceRepository` owns report/review/playbook reads and mutations,
`ManualUploadRepository` owns upload receipts, and `LocalOperationsRepository` owns operations
records. Their table ownership does not overlap.
Known callers: supported services, routes, seed/evidence commands, integration tests.

Domain: validation and contracts
SSOT module/file: `packages/contracts` and `packages/review/validation.py`
Why this is authoritative: strict Pydantic models own structural validation and the review
validator owns cross-record semantic acceptance. Generated JSON Schemas mirror these models.
Known callers: every ingestion path, persistence hydration, API response models, schema guard.

Domain: rendering and browser state
SSOT module/file: `apps/web/src/App.tsx`, `pages/` and `shared.tsx`
Why this is authoritative: `App.tsx` owns principal state and routing; each page owns its local view state;
it delegates all server interaction to `apiRequest`.
Known callers: `apps/web/src/main.tsx` and Playwright/Vitest suites.

Domain: scheduling
SSOT module/file: none
Why this is authoritative: the current product has no scheduler or background job contract;
retention and maintenance are explicit authenticated operations. The worker is health/readiness
scaffolding only.
Known callers: none.

## Retired provider experiments

The provider SDK, CLI process runner, preflights, execution factory, mock-provider harnesses,
provider-only fixtures, settings and five generated metadata schemas have been removed. No
provider credential or model selector is part of current configuration. `local_dev` supports
fixture processing and strict invented-transcript import only; `live_test` is invalid.

Historical migration files, the three media/provider metadata tables, and serialized review
provenance enum values remain for data readability and existing retention operations. They are
compatibility data, not active transports. There is no provider-attempt writer. Migration tests
insert invented historical rows and verify they survive migration replay unchanged. Historical
reports outside the repository are not rewritten or deleted. No retirement work remains open.

## Enforcement

Role/error guards, strict transcript schemas, retired-path/config assertions, dependency pins,
integration tests and browser journeys protect the supported entry points. UI pages share API
access and presentation helpers; they do not own separate permission or request policies.
