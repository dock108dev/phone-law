# Logging and secret-handling policy

Application logs are newline-delimited JSON and contain only event, service, timestamp, level,
component, opaque correlation ID, safe health route, HTTP method, status, duration, profile,
version, migration boolean, and a named error code. Unknown metadata keys are dropped.

The following are forbidden in logs: transcript or analysis text, audio, caller/staff identity,
phone number, request/query bodies, authorization or cookie headers, secrets, database/provider
URLs, exception details, and provider payloads. Uvicorn, worker HTTP, and SQL access logs are
disabled.

The local CLI boundary additionally forbids a rendered command string, raw argument dump, raw
stdout/stderr, absolute media path, complete child environment, credential value, project
identifier value, provider response, or transcript content in logs and evidence. Sanitized
provenance may contain only the transport name, declared contract, observed version or
`unavailable`, model, response format, SHA-256 input fingerprint, bounded attempt number, and
result kind. Preflight records only booleans, classifications, exact public version metadata, and
the chosen fallback.

`.env` files, private keys, credentials, and generated evidence are ignored. `.env.example`
contains only a local non-deployable demo credential. `scripts/secret_scan.py` checks forbidden
filenames and high-signal credential formats without printing matched values.

Deployment credentials must come from a future firm-owned secret manager. They must not appear
in Compose files, image layers, frontend variables, screenshots, incident tickets, or chat.
