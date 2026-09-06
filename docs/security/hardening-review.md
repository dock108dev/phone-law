# Repository security hardening review

Reviewed: 2026-09-06. Scope: working source on base `5a59ead`, including the
preserved error-handling handoff and the security changes below. This is a local
engineering review, not a penetration test, owner acceptance or production
approval. Validation is recorded in [the current check record](security-validation.md).

## Security understanding

The browser talks to the Vite local web service, which proxies `/api` to FastAPI. FastAPI resolves
one allowlisted demo principal on every review, upload, and operations route; privileged actions
also enforce administrator/operations roles server-side and append content-free audit records.
The API and worker talk to one local PostgreSQL database. The worker exposes health only and has no
queue consumer or job surface. Manual upload is the only browser file-input boundary and accepts
one bounded, allowlisted generated audio artifact or one strict invented transcript artifact.
All HTTP body consumption is now bounded and arbitrary audio is rejected before decoding.

No callback, webhook, payment, reset, invite, cookie, bearer-token, multi-tenant, or outbound-link
surface exists. The separately gated transcription SDK/CLI code is unreachable from the normal
demo stack. Local published ports bind to loopback. Staging and production configuration rejects
fake authentication, fixture adapters, local storage/databases, weak secrets, missing retention,
debug mode, permissive CORS, and local trusted hosts; a real SSO implementation and deployment
stack do not yet exist.

## Confirmed vulnerabilities fixed in this review

### SEC-001 — Unbounded JSON body consumption before authentication

- Category: API input / resource exhaustion
- Affected area: FastAPI request parsing for review and configuration mutations
- Severity: medium in this loopback synthetic application
- Confidence: high
- Why it matters: typed JSON bodies were buffered before authentication dependencies
  without an application byte cap. Upload-specific checks did not cover these routes.
- Realistic abuse: a client able to reach the local API sends a very large POST,
  consuming memory before its missing/invalid identity is rejected. Browser access
  to loopback depends on browser/network policy; this is not a claim of universal
  cross-site reachability or cross-user access.
- Evidence: `review_routes.py` and `operations_routes.py` accept typed body models;
  the previous `app.py` installed no body-consumption limit. New raw-ASGI tests
  exercise chunked and understated-length input, not just declared lengths.
- Fix: `RequestBodyLimitMiddleware` rejects malformed/duplicate Content-Length and
  declared oversize before body reads, and bounds actual consumed bytes without
  forwarding the crossing chunk. Default cap is 1 MiB; transcript upload retains
  256 KiB, audio retains configured media bytes plus 64 KiB multipart overhead.
  A 413 retains the safe error envelope, correlation ID and security headers.
  Upload authorization still runs before body consumption; the middleware does
  not pre-buffer requests. This caps application aggregation, not the transport's
  individual ASGI chunk allocation or the total across simultaneous connections.
- Status: fixed.

## Hardening opportunities implemented in this review

### SEC-002 — Framework validation errors echo rejected input

- Category: privacy / error responses
- Affected area: FastAPI body, path and query validation
- Severity: medium
- Confidence: high
- Why it matters: FastAPI's default 422 details include rejected values and can
  include caller-controlled field names, conflicting with content-free errors.
- Realistic abuse: an accidental private value in a malformed request is echoed
  into a response and may be copied into client diagnostics or incident evidence.
  No cross-user disclosure has been demonstrated.
- Evidence: there was no `RequestValidationError` handler; a regression submits a
  private sentinel and checks both the response and logs.
- Fix: a stable `request_validation_failed` envelope with correlation ID and a
  warning event replaces raw validation details. No rejected input, field names,
  validator context or request body is emitted.
- Status: fixed.

### SEC-003 — Unknown audio reached a native parser before fingerprint rejection

- Category: file upload / parser attack surface
- Affected area: `ManualUploadService.submit_audio`
- Severity: medium
- Confidence: high
- Why it matters: the synthetic-only promise does not protect a decoder if the
  generated-media allowlist is checked only after decoding.
- Realistic abuse: a local client choosing an allowed demo operations/admin
  identity supplies crafted media with a supported signature to invoke ffprobe
  before the fingerprint rejection. No decoder exploit was demonstrated.
- Evidence: the prior call order allocated/wrote a file and called `inspect`
  before `SyntheticFingerprintManifest.entry`.
- Fix: hash bounded request bytes and check the private manifest first. Unknown
  audio is rejected before file allocation, decoder invocation or receipt/processing writes (the route authorization audit
  may already exist);
  inspected bytes must still match that fingerprint. Unknown corrupt/overlong
  audio now receives `synthetic_fingerprint_not_allowlisted` before format-specific
  diagnostics. Accepted generated media retains full inspection/normalization.
- Status: fixed.

### SEC-004 — Media subprocesses inherited available network protocols

- Category: integration / defense in depth
- Affected area: ffprobe inspection and ffmpeg normalization
- Severity: medium
- Confidence: high for missing restriction; no confirmed SSRF exploit
- Why it matters: media parsing only needs local files, but the commands did not
  explicitly restrict protocols supported by the binaries.
- Realistic abuse: a referenced resource in a future accepted media format could
  reach an unintended network location if parser behavior and network access
  permit it. The earlier signature/allowlist controls limit this scenario.
- Evidence: subprocess argument lists previously lacked `-protocol_whitelist`.
- Fix: both input commands specify `-protocol_whitelist file`. Tests assert it on
  inspection, normalization and output inspection; the installed ffprobe also
  rejects an HTTP URL with that policy. This is not a filesystem sandbox or a
  substitute for private network and process-resource limits.
- Status: fixed.

## Previously fixed controls retained

The evidence descriptions below refer to the older pre-fix source, not new gaps
in the September source. Current tests continue to exercise these controls.

### Unvalidated HTTP Host header

- Category: request routing and deployment boundary
- Affected area: FastAPI application entry
- Severity: medium
- Confidence: high
- Why it matters: accepting arbitrary hosts can enable host-header poisoning when absolute URLs,
  upstream caches, or proxy routing are introduced.
- Realistic scenario: a future proxy forwards an attacker-controlled `Host`; application or proxy
  behavior then uses it for routing or generated links.
- Evidence: `create_app` configured CORS but had no trusted-host middleware or host configuration.
- Fix: added typed `TRUSTED_HOSTS`, strict hostname syntax, local Compose defaults, deployment
  validation that rejects wildcards/local demo names, and `TrustedHostMiddleware`.
- Status: fixed and tested.

### Missing defensive browser and API response headers

- Category: browser security and data exposure
- Affected area: FastAPI responses and Vite local web service
- Severity: medium
- Confidence: high
- Why it matters: without explicit policy, internal pages may be framed, indexed, cached, or given
  broader browser capabilities than intended.
- Realistic scenario: a user opens the local interface through an untrusted embedding page, or an
  intermediary/browser retains a sensitive synthetic response after the product later handles
  approved data.
- Evidence: neither `create_app`, `vite.config.ts`, nor `index.html` set CSP, frame, referrer,
  permissions, MIME-sniffing, cache, opener/resource, or noindex controls.
- Fix: added `no-store`, CSP, frame denial, `nosniff`, no-referrer, permissions denial,
  same-origin resource policy, and noindex headers; HTML also carries a robots meta tag. API
  responses also set same-origin opener policy.
- Status: fixed and tested. The Vite CSP permits inline scripts/styles and WebSocket connections
  only because the development server injects its client bootstrap and hot-reload transport. An
  optional direct API origin is added only when it is plain HTTP on the fixed local
  `api`/`localhost`/`127.0.0.1` host allowlist with no credentials, path, query, or fragment. Vite
  is not an approved production server. Production must use nonce/hash-based scripts and exact
  connection origins at the approved reverse proxy. The web development server intentionally
  omits opener policy because Chromium ignores it on the isolated non-localhost HTTP test origin;
  enable it at the approved trustworthy HTTPS ingress.

### Unexpected failures obscured security-relevant state (retained)

- Category: auditability and incident response
- Affected area: upload routes/service, transcription adapter, operations reconciliation
- Severity: medium
- Confidence: high
- Why it matters: a programming defect or malformed persisted state could look like a handled
  success/provider failure and delay investigation.
- Realistic scenario: an unexpected analysis defect returns HTTP 200, or missing reconciliation
  appears as exact zero activity.
- Evidence: broad catches returned a failed receipt with HTTP 200; unknown adapter exceptions were
  classified as provider failures; absent reconciliation returned `exact=true`.
- Fix: preserved safe durable state and cleanup but escalated unexpected defects with correlation-
  bound events and HTTP 500; unknown adapter defects re-raise; unavailable/malformed
  reconciliation is explicit or fails closed.
- Status: fixed and tested in the preceding error-handling slice.

## Intentional acceptable patterns

### Spoofable demo identity header

- Affected area: `demo_principal` and the local role selector
- Category: authentication
- Severity: informational in current scope; critical if exposed as production authentication
- Confidence: high
- Evidence: `X-Demo-Principal` selects one allowlisted fictional identity. Client-supplied role is
  ignored, and the dependency returns 404 outside test/demo profiles.
- Rationale: this is a loopback synthetic demonstration with no real users or data. Server-side
  authorization still enforces each role.
- Status: accepted locally; prohibited in staging/production.

### No CSRF token or secure cookie policy

- Affected area: browser-to-API requests
- Category: browser session security
- Severity: informational
- Confidence: high
- Evidence: the application has no cookie-backed session or browser credential. CORS disallows
  credentials and only allowlists the local origin.
- Rationale: there is no ambient credential for a cross-site request to reuse.
- Status: accepted for the local demo; reassess with firm SSO/session design.

### Content-bearing framework logs disabled

- Affected area: API/worker HTTP and SQL logging
- Category: logging and privacy
- Severity: informational
- Confidence: high
- Evidence: Uvicorn access/error and SQL logs are disabled; allowlisted application events and
  durable audit/failure states remain.
- Rationale: raw request/exception/database logs could expose future restricted content or
  credentials. Correlation IDs, sanitized source locations (without exception text or locals), and
  deterministic reproduction are the supported diagnostic path.
- Status: accepted and documented.

## Deferred findings requiring decisions

### Firm authentication and centralized authorization

- Category: authentication and authorization
- Severity: high production blocker
- Confidence: high
- Evidence: production settings require `AUTH_MODE=sso`, but no SSO/session verifier, firm identity
  mapping, revocation, or centralized policy component exists.
- Recommended path: choose the firm identity provider; define session lifetime, MFA, role source,
  revocation, break-glass, audit, and account lifecycle; implement and test server-side policy.
- Status: deferred; staging/production must remain inaccessible.

### Abuse controls and resource quotas

- Category: availability and workflow abuse
- Severity: high before any non-loopback ingestion; low in the current local demo
- Confidence: high
- Evidence: uploads are byte/duration bounded and mutations are role/idempotency guarded, but no
  per-identity/IP rate limiter, concurrency quota, or upstream body/connection limit exists.
- Recommended path: enforce body and connection limits at approved ingress, then add distributed
  identity-aware quotas for upload, retry, publication, retention, and drill actions with safe
  metrics and operator override policy.
- Status: deferred pending ingress and identity architecture.

### TLS, HSTS, ingress, and network policy

- Category: transport and deployment
- Severity: high production blocker
- Confidence: high
- Evidence: local services use HTTP and loopback/Compose networking; no production proxy or TLS
  termination exists. HSTS is intentionally absent because emitting it before HTTPS is enforced is
  unsafe and misleading.
- Recommended path: select private ingress/TLS termination, restrict service/database networks,
  preserve the defensive headers, and add HSTS after the final HTTPS domain and preload policy are
  approved.
- Status: deferred.

### Managed secrets, key rotation, and production storage

- Category: secrets and data protection
- Severity: high production blocker
- Confidence: high
- Evidence: deployment validation requires non-placeholder settings, but the repository contains
  no firm secret manager integration, rotation/revocation procedure, private object store adapter,
  encryption-key ownership, backup key handling, or approved retention policy.
- Recommended path: integrate firm-owned secret delivery and private storage, define encryption
  and rotation ownership, validate backup/restore and deletion, and prohibit secrets in Compose,
  images, browser variables, logs, evidence, and chat.
- Status: deferred.

## Manual verification outside this repository

- Confirm approved DNS, TLS certificate lifecycle, reverse-proxy header preservation, body/time
  limits, firewall/private-network rules, database TLS and least privilege.
- Confirm SSO tenant restrictions, MFA, group-to-role mapping, offboarding/revocation, session and
  cookie flags, CSRF posture, and security-event delivery.
- Confirm cloud object/database encryption, regional/data-control requirements, backup access,
  retention/deletion evidence, central log access/retention, alert thresholds, and incident drills.
- Re-run dependency advisory checks and image/SBOM/signature scanning in the chosen CI/registry;
  local advisory results are a point-in-time check only.

## Prioritized remaining roadmap

1. **High / needs decision — production identity and access.** Keep deployment
   blocked until the firm selects SSO, MFA, authoritative roles, session/revocation
   and audit policy; implement server-side verification and negative authorization
   tests. Scope is auth/session entry and every privileged route. Confidence high;
   local demo identity impersonation is intentional, unsafe on a public service.
2. **High / deferred — ingress and shared resource controls.** Define TLS/private
   ingress, connection/read timeouts, concurrent request limits and identity-aware
   quotas. Request byte caps do not stop slow uploads or many concurrent small
   requests. Add process memory/CPU limits and parser isolation before real media.
   Confidence high from the absence of these deployment controls in Compose.
3. **High / needs decision — private data and secrets.** Select managed secrets,
   storage, encryption/key ownership, least-privilege DB roles, retention and backup
   policy. Current demo DB credentials and local storage must never be reused for
   real data. Confidence high; adapters and operational ownership are absent.
4. **Medium / deferred — crash recovery and security-event operations.** Add
   durable stale-job recovery, centralized log access/retention, alert routing and
   drills before production. Sanitized logs are evidence, not an alerting service.
5. **Manual verification — deployment evidence.** Validate actual IdP policy,
   network reachability, TLS/header preservation, image/SBOM/advisory scans,
   encryption, backup access and deletion outside this repository. Repository
   tests cannot establish those properties. Re-run hosted CI/CodeQL on the final
   committed candidate; this local review does not certify them.
