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
| Retention | `AUDIO_RETENTION_DAYS`, `TRANSCRIPT_RETENTION_DAYS`, `ANALYSIS_RETENTION_DAYS`, `AUDIT_RETENTION_DAYS`, `RETENTION_POLICY_APPROVED` |
| HTTP and operations | `DEBUG`, `CORS_ORIGINS`, `TRUSTED_HOSTS`, `FIRM_TIMEZONE`, `LOG_LEVEL` |

The browser has a separate build-time boundary: `VITE_APP_PROFILE` accepts only `test` or `demo`,
and `VITE_ALLOW_REAL_CALL_DATA` must be `false`. `VITE_API_BASE_URL` optionally selects the API
origin; otherwise Vite proxies `/api` through `VITE_API_PROXY_TARGET`, which defaults to
`http://api:8000`. None of the `VITE_*` variables may contain credentials or secrets.

## Local-development profile

`local_dev` is synthetic-only and supports fixture processing or strict transcript-only import.
The accepted adapter triples are `fixture` / `fixture` / `fixture` and
`transcript_only` / `transcript_only_import` / `fixture`. Its media root remains
`/tmp/colacci-law-slice3c/objects` for the supported importer. The application uses `demo` or `test`.
Provider settings and the historical live profile have been removed.

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

| Profile | Purpose | Real data | Adapters | Storage/auth |
|---|---|---|---|---|
| `test` | Deterministic automated checks | Always rejected | Fixture adapters | Local synthetic/fake |
| `demo` | Default local application | Always rejected | Fixture adapters | Local synthetic/fake |
| `local_dev` | Offline transcript-only development | Always rejected | Exact allowlisted synthetic triples | Temporary local synthetic/fake |
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

## Provider execution is unsupported

No provider credential, endpoint, model, execution gate or CLI capability is consumed by current
settings. Generated media remains bounded to local synthetic roots. Historical database and
provenance compatibility do not enable execution.
