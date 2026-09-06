# Logging and secret-handling policy

Application logs are newline-delimited JSON and contain only event, service, timestamp, level,
component, opaque correlation ID, safe health route, HTTP method, status, duration, profile,
version, migration boolean, a named error code, exception class and bounded repository-relative
source locations. Source locations omit raw exception text, locals, absolute paths and source lines. Unknown metadata keys are dropped.

The following are forbidden in logs: transcript or analysis text, audio, caller/staff identity,
phone number, request/query bodies, authorization or cookie headers, secrets, database/provider
URLs, raw exception details, rejected validation inputs, and provider payloads. Uvicorn, worker HTTP, and SQL access logs are
disabled.

Historical provider provenance may remain in stored records, but it is never authorization to
execute a provider request. Provider/CLI tooling and credential configuration are removed.

Manual-upload request bodies, multipart headers, selected filenames, full content fingerprints,
object IDs, local paths, transcript content, and raw exceptions are also excluded. Upload routes
emit only the allowlisted HTTP envelope; application errors return a stable code and opaque
correlation ID. The focused browser command scans API and worker logs after the complete upload
lifecycle.

`.env` files, private keys, credentials, and generated evidence are ignored. `.env.example`
contains only a local non-deployable demo credential. `scripts/secret_scan.py` checks forbidden
filenames and high-signal credential formats without printing matched values.

Deployment credentials must come from a future firm-owned secret manager. They must not appear
in Compose files, image layers, frontend variables, screenshots, incident tickets, or chat.

HTTP body rejections emit `request_body_rejected` with `invalid_content_length`
or `request_body_too_large`; model validation emits `request_validation_rejected`
with `request_validation_failed`. Both are warning events with correlation IDs.
Default framework validation bodies are not returned to the client.
