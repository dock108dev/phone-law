# Environment profiles and configuration rules

## Configuration sources and variable groups

`packages/config/settings.py` is the typed authority for API, worker, migration, and command-line
settings. `.env.example` lists every operator-settable field with non-deployable local defaults;
Docker Compose fixes the normal demo values and injects `SERVICE_NAME` separately for API and
worker. Pydantic reads names case-insensitively and ignores unknown environment keys, but engineers
should not rely on ignored keys as configuration.

| Group | Variables |
|---|---|
| Profile and version | `APP_PROFILE`, `APP_VERSION` |
| Real-data guard | `ALLOW_REAL_CALL_DATA`, `REAL_CALL_PROCESSING_AUTHORIZED`, `REAL_DATA_APPROVAL_REFERENCE` |
| Authentication and database | `AUTH_MODE`, `APP_SECRET`, `DATABASE_URL` |
| Adapter selection | `CALL_SOURCE_ADAPTER`, `TRANSCRIBER_ADAPTER`, `ANALYZER_ADAPTER`, `NOTIFICATION_ADAPTER` |
| Storage and media | `OBJECT_STORAGE_BACKEND`, `OBJECT_STORAGE_BUCKET`, `MEDIA_TEMP_ROOT`, `MANUAL_UPLOAD_ROOT`, `MANUAL_UPLOAD_MANIFEST_PATH`, `MEDIA_MAX_BYTES`, `MEDIA_MAX_DURATION_SECONDS` |
| Transcription gate | `LIVE_TRANSCRIPTION_ENABLED`, `LIVE_TRANSCRIPTION_AUTHORIZED`, `TRANSCRIPTION_APPROVAL_REFERENCE`, `TRANSCRIPTION_MODEL_ID`, `TRANSCRIPTION_FALLBACK_MODEL_ID`, `TRANSCRIPTION_TIMEOUT_SECONDS`, `TRANSCRIPTION_MAX_REQUESTS`, `TRANSCRIPTION_MAX_TOTAL_AUDIO_SECONDS`, `TRANSCRIPTION_MAX_TOTAL_BYTES`, `TRANSCRIPTION_TEST_BUDGET_USD`, `TRANSCRIPTION_LIVE_EXECUTION_CONFIRMED`, `TRANSCRIPTION_LIVE_EXECUTION_AUTHORIZATION_ID` |
| Provider preconditions | `OPENAI_API_KEY`, `OPENAI_PROJECT_ID`, `OPENAI_BASE_URL`, `FIRM_OWNED_OPENAI_PROJECT_NAMED`, `OPENAI_PROJECT_OWNERSHIP_APPROVED`, `OPENAI_PROJECT_DATA_CONTROLS_APPROVED`, `OPENAI_PROVIDER_TERMS_APPROVED`, `GENERATED_AUDIO_TEST_APPROVED` |
| Retention | `AUDIO_RETENTION_DAYS`, `TRANSCRIPT_RETENTION_DAYS`, `ANALYSIS_RETENTION_DAYS`, `AUDIT_RETENTION_DAYS`, `RETENTION_POLICY_APPROVED` |
| HTTP and operations | `DEBUG`, `CORS_ORIGINS`, `TRUSTED_HOSTS`, `FIRM_TIMEZONE`, `LOG_LEVEL` |

The browser has a separate build-time boundary: `VITE_APP_PROFILE` accepts only `test` or `demo`,
and `VITE_ALLOW_REAL_CALL_DATA` must be `false`. `VITE_API_BASE_URL` optionally selects the API
origin; otherwise Vite proxies `/api` through `VITE_API_PROXY_TARGET`, which defaults to
`http://api:8000`. None of the `VITE_*` variables may contain credentials or secrets.

Blank provider fields in `.env.example` document the complete shape only. Credentials and approval
identifiers must come from a separately approved ephemeral environment and must never be saved in
`.env`, Compose, shell history, logs, screenshots, or evidence.

## Local-development profile

`local_dev` remains synthetic-only and rejects both live-transcription flags, an approval
reference, real data, non-local storage, real notifications, and non-fake authentication. Its
media root is fixed at `/tmp/colacci-law-slice3c/objects`. Only these adapter triples are valid:

- `fixture` / `fixture` / `fixture`
- `generated_synthetic` / `openai_cli_local` / `disabled`
- `transcript_only` / `transcript_only_import` / `fixture`

The local CLI transport is not selected by an ambient credential. Exact capability preflight is
required first; an unsupported result keeps the process on the fixture/transcript-only fallback.
The normal Compose services remain `demo`, and their application factories do not construct a
CLI client.

## Local demo boundary

The `demo`, `test`, and `local_dev` profiles may use `LocalSyntheticObjectStore` only beneath an
absolute `/tmp/colacci-law-slice4-*` root. The default manual-upload root and private fingerprint
manifest are fixed configuration values, not request fields. The root is `0700`, objects and the
manifest are `0600`, symlinks are rejected, and the configured media caps remain 20 MiB and 60
seconds. `staging` and `production` cannot activate this local bridge. Live-transcription flags,
real-data flags, remote storage, real notification, and non-fake authentication remain rejected in
the local profiles.

## Versioned local firm configuration

The operational policy is persisted separately from process environment settings as immutable
`local-firm-configuration-v1` rows. The exact contract includes the local timezone and report
cutoff, eligible synthetic directions/categories, invented staff-extension mappings, demo report
roles, synthetic playbook identifier, nine synthetic retention durations, scheduled destruction
with a tombstone, and `local_preview_noop`. Unknown fields and production-shaped values are
rejected. Only the server-resolved demo administrator may publish the next version. Demo
operations may review configuration history but cannot publish.

`America/New_York` is the explicit local default only. The retention values are accelerated
synthetic defaults only. Neither represents client approval. See [the operator guide](local-operations.md).

## Gated live-test profile

`live_test` is a fail-closed, generated-media-only verification profile. It requires the
exact owner authorization, the approved transcription model, an explicit project-scoped
credential, official OpenAI endpoint selection, and the exact request, retry, duration,
byte, and application-budget caps. It disables analysis, notifications, real-data modes,
manual upload, and Broadvoice. The normal application and Compose defaults remain the
offline `demo` profile.

Use `make transcription-live-preflight` first. It runs without network access and emits
sanitized evidence at
`/tmp/colacci-law-slice3b-final-preflight/evidence/slice3b-final-preflight.json`. Only a fresh passing report
allows `make test-transcription-live`, which also requires
`TRANSCRIPTION_LIVE_EXECUTION_CONFIRMED=true`. Credentials must arrive through an
approved ephemeral environment and must never be written to `.env` or repository files.
The account-specific data-control state must also be explicitly attested with
`OPENAI_PROJECT_DATA_CONTROLS_APPROVED=true`; credentials alone do not satisfy the gate.

| Profile | Purpose | Real data | Adapters | Storage/auth |
|---|---|---|---|---|
| `test` | Deterministic automated checks | Always rejected | Fixture adapters | Local synthetic/fake |
| `demo` | Default local application | Always rejected | Fixture adapters | Local synthetic/fake |
| `local_dev` | Bounded local CLI or transcript-only development | Always rejected | Exact allowlisted synthetic triples | Temporary local synthetic/fake |
| `live_test` | Owner-gated generated-audio verification | Always rejected | Gated file transcription; analysis disabled | Temporary local synthetic/project credential |
| `staging` | Future firm-owned preproduction | Disabled unless separately authorized | Fixture adapters rejected | Private cloud/SSO required |
| `production` | Future authorized deployment | Disabled unless separately authorized | Fixture adapters rejected | Private cloud/SSO required |

The default is `demo` and `ALLOW_REAL_CALL_DATA=false`. Its only call-submission route accepts
allowlisted generated non-human audio or a strict invented transcript artifact; report and review
routes otherwise read committed synthetic data and append synthetic human-review events.

For `staging` or `production`, startup rejects:

- authentication other than `sso`;
- missing, short, demo, example, placeholder, local, or test secrets;
- storage other than `private_cloud`, or an example/missing bucket;
- fixture call source, transcriber, or analyzer;
- any call source except `disabled` or the future `manual_upload` boundary;
- any transcriber or analyzer other than `disabled` in this slice;
- unapproved or non-positive audio, transcript, analysis, or audit retention;
- debug mode;
- empty, wildcard, non-HTTPS, or localhost CORS origins;
- local, example, placeholder, or weak database configuration;
- real-call mode without both explicit authorization and a non-placeholder approval reference.

Real-call authorization is represented in validation so it can fail closed, but this does not
grant authority and does not make real processing available. The roadmap preflight remains a
separate stop condition.

`TRUSTED_HOSTS` is a JSON list of lowercase DNS names or literal IPv4 host values accepted by the
API. The local Compose default is limited to `localhost`, `127.0.0.1`, and the named internal
Compose/test services. Staging and production must replace that list with approved deployment DNS
names; wildcards, local names, and internal demo service names fail startup validation.

Configuration values are never dumped or included in an exception log. Only the content-free
`unsafe_configuration` code is emitted when process startup is rejected.

## Normal profiles remain offline

- `LIVE_TRANSCRIPTION_ENABLED=false`
- `LIVE_TRANSCRIPTION_AUTHORIZED=false`
- `TRANSCRIPTION_APPROVAL_REFERENCE=`

These defaults remain enforced for `test`, `demo`, `staging`, and `production`; any live flag or
approval reference is rejected outside the exact `live_test` profile. An ambient API key is not
authority. Generated media is confined beneath an explicit `/tmp/colacci-law-*` root, the
application cap defaults to 20 MB and can never exceed the current documented 25 MB provider
ceiling, and the conservative synthetic duration cap is 60 seconds.
