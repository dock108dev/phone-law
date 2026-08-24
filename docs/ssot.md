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
Why this is authoritative: all API/authentication errors use its sanitized error and correlation
shape.  
Known callers: demo authentication and all three API routers.

Domain: browser API access  
SSOT module/file: `apps/web/src/api.ts`  
Why this is authoritative: browser requests, demo identity headers, response parsing, and safe
client errors all pass through `apiRequest`.  
Known callers: `apps/web/src/App.tsx`.

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
SSOT module/file: `apps/web/src/App.tsx`  
Why this is authoritative: it is the single mounted application state and route rendering tree;
it delegates all server interaction to `apiRequest`.  
Known callers: `apps/web/src/main.tsx` and Playwright/Vitest suites.

Domain: scheduling  
SSOT module/file: none  
Why this is authoritative: the current product has no scheduler or background job contract;
retention and maintenance are explicit authenticated operations. The worker is health/readiness
scaffolding only.  
Known callers: none.

## Conflict inventory and disposition

| Candidate | Usage finding | Disposition |
|---|---|---|
| Route-local role sets and direct `DemoRole` conditionals | Repeated in review, upload, operations, capabilities, and repository checks | Removed; all decisions route through `demo_policy.py` |
| Three route-local `_error()` implementations plus auth-specific detail construction | Same response contract implemented four times | Removed; all use `api_error()` |
| `Transcript.provider_response_version="legacy-review-contract-v1"` | Silent compatibility fallback; every supported producer already supplies an explicit version | Removed; field is required and schema/test guarded |
| `packages.database.local_operations.default_configuration()` | No runtime, script, or test caller | Removed; callers use the validated contract constant |
| Alembic `0006` default-configuration payload | Historical migration snapshot, not runtime policy | Retained so old databases migrate deterministically; current policy remains the contracts model |
| Local CLI capability fallback | Called by stable preflight/offline Make targets and recorded by ADR 0008 | Retained as an explicit zero-request engineering path, not an application fallback |
| `live_test` adapter and gates | Called by separate preflight/live commands and protected by an owner authorization contract | Retained outside normal factories; retirement would require a separate owner decision |
| Staging/production configuration validation | No deployable adapters exist, but the guard prevents unsafe accidental startup | Retained as an explicit failure boundary, not represented as production capability |

## Enforcement guards

`tests/unit/test_demo_authorization.py` locks the exact permission matrix and derived operations
actions. `tests/unit/test_ssot_guards.py` prevents route-local role/error policy, the legacy
transcript fallback, and the unused default wrapper from returning. Supported producers and the
generated transcript schema must require an explicit provider response version.
