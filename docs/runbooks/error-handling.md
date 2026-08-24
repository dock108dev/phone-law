# Error handling and incident diagnosis

This application keeps responses and logs free of call content, credentials, request bodies,
provider payloads, local paths, and raw exception text. That privacy boundary does not make
failures optional: production-path failures must appear as a non-success HTTP response, a named
durable state, or an allowlisted operational event with an opaque correlation ID.

## Request failures

Every HTTP request receives an `X-Correlation-ID`. A safe caller-provided value is retained;
otherwise the API generates one. Successful and handled requests emit `http_request_completed`.
An exception that escapes a route emits `http_request_failed` and is re-raised. Manual-upload
routes keep a sanitized stable error response, preserve the exception chain, and emit
`manual_upload_request_failed` for unexpected request or persistence defects.

Do not add request bodies, headers, query strings, filenames, object identifiers, complete content
hashes, exception messages, or stack traces to application logs. Reproduce against the exact
source revision with synthetic inputs and use the correlation ID, safe event, receipt state,
audit history, and deterministic test case to isolate the failure.

## Manual-upload state transitions

Expected validation, conflict, missing-receipt, deterministic transcription, deterministic
analysis, and deletion failures remain typed outcomes. Retryable deterministic failures retain
their bounded retry action. Terminal outcomes remove temporary media when possible and persist a
safe diagnostic code.

An unexpected transcript or audio processing defect is different. The service first persists an
`analysis_failed` or `deletion_failed` receipt and attempts required media cleanup. It then emits
`manual_upload_processing_failed` and escalates to the route, which returns HTTP 500 with
`manual_upload_failed`. A refresh of the upload queue shows the durable sanitized receipt. The API
must not return HTTP 200 for this condition.

For `temporary_media_deletion_failed`, stop processing that receipt. Confirm the local synthetic
object root is available and use only the documented cleanup/retry flow. Do not delete database
rows or temporary paths manually during evidence collection.

## Transcription retries and fallback

The SDK adapter retries only classified connection/timeout, rate-limit, and provider 5xx failures,
with at most three provider attempts and bounded delays. Authentication, permission, invalid
request, invalid response, and safe transport-boundary failures are terminal. An exception outside
those expected SDK/validation families is a programming or integration defect and is re-raised;
it is not recorded as a provider failure.

The local CLI capability probe may select `fixture-and-transcript-only` when the executable is
absent, unsupported, times out, or exposes the wrong command surface. This is intentional because
the selected capability and fallback are explicit, no provider request is made, and the offline
contract gate records the decision. Temporary CLI cleanup records a cleanup confirmation; a false
confirmation fails the focused proof.

## Health, auth audit, and framework-log suppression

Database readiness converts SQLAlchemy connectivity/schema failures into HTTP 503 with the safe
`database_unavailable_or_unmigrated` code. It does not claim readiness. Demo authorization audit is
best effort so a broken audit insert cannot turn an allowlisted local denial into access; the API
emits `authorization_audit_unavailable` when that fallback is used.

The Operations overview reports `available=false` and `exact=false` when no current daily report
exists. A persisted report with a missing, negative, boolean, or non-integer reconciliation value
is treated as invalid and fails the request. It is never converted into zero-count exact success.

Uvicorn access/error and SQL logs remain disabled because they may include paths, headers,
database details, or exception content. The allowlisted application events, correlation IDs,
durable receipt/deletion states, audit records, and deterministic reproduction are the supported
operational surfaces.

## Validation and triage

Start with the smallest relevant deterministic test, then run the repository gates after the last
source change. For upload or adapter changes, run at minimum:

```bash
make lint
make typecheck
make test
make test-integration
make test-transcription-contract
make test-manual-upload
git diff --check
```

Keep live transcription disabled unless the separately documented owner authorization and live
preflight are current. Do not use real or human recordings to reproduce an incident in this local
synthetic repository.
