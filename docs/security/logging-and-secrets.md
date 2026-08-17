# Logging and secret-handling policy

Application logs are newline-delimited JSON and contain only event, service, timestamp, level,
component, opaque correlation ID, safe health route, HTTP method, status, duration, profile,
version, migration boolean, and a named error code. Unknown metadata keys are dropped.

The following are forbidden in logs: transcript or analysis text, audio, caller/staff identity,
phone number, request/query bodies, authorization or cookie headers, secrets, database/provider
URLs, exception details, and provider payloads. Uvicorn, worker HTTP, and SQL access logs are
disabled.

`.env` files, private keys, credentials, and generated evidence are ignored. `.env.example`
contains only a local non-deployable demo credential. `scripts/secret_scan.py` checks forbidden
filenames and high-signal credential formats without printing matched values.

Deployment credentials must come from a future firm-owned secret manager. They must not appear
in Compose files, image layers, frontend variables, screenshots, incident tickets, or chat.
