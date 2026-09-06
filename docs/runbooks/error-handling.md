# Failure handling and operations

This describes the implemented synthetic/local application, not a production
approval. Production profiles remain blocked by configuration. There is no
queue consumer, scheduled processing service, or production alert backend: the
worker currently serves health checks only. Real data, provider execution and
notifications require their separate authorization gates.

## HTTP and diagnostics

Unexpected API exceptions produce HTTP 500 with
`{"detail":{"error":"internal_error","correlation_id":"…"}}`. The response
retains `X-Correlation-ID`, `Cache-Control: no-store` and security headers.
Upload routes retain their specific sanitized error envelope. Expected input,
permission, missing-receipt and conflict errors remain 4xx. Upload `KeyError`
and `IndexError` are programming faults and produce 500, not a misleading 404.

Every request completed by the operational middleware is logged (CORS
preflight is handled by the outer CORS middleware): 5xx at error, 4xx at warning, other responses
at info. Each unexpected middleware failure also emits `http_request_failed`;
upload boundaries emit `manual_upload_request_failed` or
`manual_upload_processing_failed`. Repeated failures are not deduplicated.
These events are not independent request counts: join them using correlation ID.
Allowed cross-origin responses expose the correlation header to the browser.

`OperationalLogger.exception` records exception class and up to 32 repository
source locations in `exception_frames` (repository-relative file and line).
It deliberately excludes exception messages, locals, source text, absolute
paths, third-party frames and exception-chain text. Consult the matching source
revision to interpret these locations. This is a sanitized stack, not a raw
traceback. Raw Uvicorn access/error and SQLAlchemy engine logging remain disabled
because they may disclose URLs, SQL values or credentials. The worker replaces
socketserver's raw exception output with `worker_health_request_failed`.
Request bodies, query strings, authorization headers and arbitrary metadata are
never passed to these diagnostics. Non-allowlisted routes are `unknown`.

The web client reports unreachable services, malformed/empty successful JSON,
and interrupted response bodies as `ApiRequestError`. Body-read failures retain
the HTTP status and correlation ID. No automatic mutation retry occurs: inspect
the saved receipt/review state before retrying an uncertain write.

Request-model validation returns 422 `request_validation_failed` without rejected
values or field details. HTTP body limits return 400 `invalid_content_length` or
413 `request_body_too_large`. Both preserve correlation IDs and emit warning
events; see the [security review](../security/hardening-review.md) for byte caps.

## Cleanup and processing

Expected fixture/transcription failures remain explicit persisted attempt or
receipt states. Retryability and attempt caps are unchanged. Unexpected manual
processing faults are logged **before** cleanup or recovery database writes, so
a second recovery failure does not erase evidence of the original defect.
Recovery writes can still fail; HTTP then reports failure, not success.

Rejected-upload cleanup attempts each distinct source/retained reference. Any
unconfirmed deletion or expected store/OS error produces
`temporary_media_cleanup_failed` and HTTP 500 `temporary_media_deletion_failed`.
This replaces an ordinary validation rejection when media may remain. No receipt
may exist yet: inspect the bounded temporary object store as well as receipts.
Do not assume the absence of a receipt proves media deletion.

The object store intentionally converts deletion OS failures to a typed
`MediaDeletionEvent` with `deletion_confirmed=false` and always emits an error
event, including normalization cleanup paths whose caller already failed. Failed
file imports attempt to delete their partial allocation before propagating the
copy/permission error. Missing files remain an
idempotent successful deletion. Persisted cancellation/processing flows expose
`DELETION_FAILED` and audit it; pre-receipt cleanup now checks the same result.
CLI transcription cannot report success after request-directory cleanup fails:
it records a false cleanup confirmation and returns terminal
`MEDIA_DELETION_FAILED`, without another provider request. Removal of the empty
shared CLI parent remains best effort after request media is confirmed gone.

The manual-upload asset cleanup command fails on OS deletion errors, including
extensionless temporary objects. An already absent tree is acceptable. It never
prints `temporary_objects=0` after a failed removal.

The SDK retry limit is three attempts for classified connection/timeout,
rate-limit and provider 5xx failures. Authentication, permission, invalid request
and invalid response failures are terminal. The CLI capability probe may select
`fixture-and-transcript-only` when its executable is absent, unsupported or
unavailable; the capability result and offline evidence expose that decision.

Operations reports `available=false` and `exact=false` when no current daily
report exists. Invalid persisted reconciliation counts fail the request instead
of becoming zero-count success.

## Incident response

1. Capture the response correlation ID, status, current source revision, safe
   error code and sanitized events. Do not copy private request/response content
   into logs or tickets. For an interrupted mutation, inspect persistent state.
2. For 503 readiness, check database reachability and migration revision against
   `packages/database/health.py`. Liveness only proves the process responds;
   readiness requires database and migration checks. Both API and worker emit
   warning events on failed readiness.
3. For processing/cleanup failure, inspect upload receipt and state events,
   processing attempts, and Operations deletion jobs. Use the existing bounded
   retry/cancel mechanisms only where the state permits them. Preserve the
   original failure before intervening.
4. If cleanup is unconfirmed, restrict access to retained temporary data and
   resolve the filesystem/storage error. Use the supported cleanup workflow for
   the correct disposable runtime; never point it at another active campaign.
5. If persistence itself failed, reconcile stuck processing/deleting state
   before resubmission. There is no automatic stale-job repair or crash-recovery
   lease. Do not mark work complete based on a log entry alone.

## Repository audit decisions (2026-09-06)

| Area / severity | Implemented outcome or retained behavior |
| --- | --- |
| HTTP/worker diagnostics — High | Sanitized source locations, stable 500 envelope and error-level 5xx reporting replace blind spots. |
| Temporary-media cleanup — High | Rejected-upload, CLI request cleanup and asset cleanup now reject false success. |
| Upload classification — Medium | Programming lookup errors are 500; explicit missing receipts remain 404. |
| Security scan — High | Unreadable/invalid UTF-8 source is a `source_unreadable` finding and fails the gate. Binary macOS `.DS_Store` is explicitly excluded. No unreadable content is printed. |
| Web fetch/render — Medium | Failed body reads and invalid successful payloads are explicit errors. Existing loading/error and uncertain-save UI is preserved. |
| Auth/audit — Note | Demo-only missing/invalid-session audit is best effort with warning on SQL failure; authentication denial still applies. Business authorization/audit writes are not suppressed. Missing engine/logger guards support isolated auth tests; deployed app construction supplies both. |
| Database transactions — Note | Integrity-race handling only returns duplicate after finding the corresponding existing receipt; otherwise re-raises. Retention OS failures persist bounded retry/terminal state; unexpected database failures propagate. |
| Review pipeline — Note | Fixture and structured-output failures persist classified terminal states; no invalid analysis is presented as successful. Retry count is bounded. |
| Media/provider boundary — Note | Inspection and subprocess failures become typed failures. Provider connection/status/response errors retain attempt classification and bounded retries; malformed Retry-After falls back to bounded delay. Model fallback metadata does not authorize a second model request. |
| Runtime/configuration — Note | Unsafe configuration exits 78 with a content-free startup event. Synthetic notification no-op and provider guards are intentional product boundaries. No warning filters or production-mode fail-open bypass were found. |
| Tooling/tests/CI — Note | Static suppressions cover fixture constants, known subprocess commands, temp roots, migration imports and integration-only coverage. Shell gates fail on errors; cleanup traps preserve ownership. Optional preflight failures return explicit capability/status failures. Disposable fixture setup has best-effort removal followed by validation; this is not production cleanup. |

## Validation and remaining boundaries

Use `make lint typecheck test build` with the pinned images. Integration tests
require an isolated PostgreSQL database ending in `_test` and generated assets.
`make test-e2e` runs disposable browser journeys, recovery and morning briefing;
choose fresh `COLACCI_E2E_PROJECT`, `SLICE4_RUNTIME_ROOT` and
`SLICE4_EVIDENCE_DIR` values. Do not run a quality container carrying that same
Compose project label concurrently with campaign cleanup.

Regression coverage includes repeated 500s, safe stack locations, worker errors,
lookup classification, recovery-write failure, cleanup after provider success,
pre-receipt cleanup, unreadable scan input, and interrupted/invalid web responses.
See `error-handling-validation.md` for this implementation's actual results.

Separate production work still needs alert routing, persistent metric storage,
crash/stale-processing recovery, and firm-owned operational controls. This change
does not run live providers, publish, commit, or qualify a new demo candidate.
