# Repository security hardening review

Reviewed: 2026-08-23. Scope: the current local synthetic source tree on
`codex/abend-handling-hardening`. This is an engineering security review, not a penetration test or
a production authorization.

## Security understanding

The browser talks to the Vite local web service, which proxies `/api` to FastAPI. FastAPI resolves
one allowlisted demo principal on every review, upload, and operations route; privileged actions
also enforce administrator/operations roles server-side and append content-free audit records.
The API and worker talk to one local PostgreSQL database. The worker exposes health only and has no
queue consumer or job surface. Manual upload is the only browser file-input boundary and accepts
one bounded, allowlisted generated audio artifact or one strict invented transcript artifact.

No callback, webhook, payment, reset, invite, cookie, bearer-token, multi-tenant, or outbound-link
surface exists. The separately gated transcription SDK/CLI code is unreachable from the normal
demo stack. Local published ports bind to loopback. Staging and production configuration rejects
fake authentication, fixture adapters, local storage/databases, weak secrets, missing retention,
debug mode, permissive CORS, and local trusted hosts; a real SSO implementation and deployment
stack do not yet exist.

## Fixed findings

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

### Unexpected failures obscured security-relevant state

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

- Category: authentication
- Severity: informational in current scope; critical if exposed as production authentication
- Confidence: high
- Evidence: `X-Demo-Principal` selects one allowlisted fictional identity. Client-supplied role is
  ignored, and the dependency returns 404 outside test/demo profiles.
- Rationale: this is a loopback synthetic demonstration with no real users or data. Server-side
  authorization still enforces each role.
- Status: accepted locally; prohibited in staging/production.

### No CSRF token or secure cookie policy

- Category: browser session security
- Severity: informational
- Confidence: high
- Evidence: the application has no cookie-backed session or browser credential. CORS disallows
  credentials and only allowlists the local origin.
- Rationale: there is no ambient credential for a cross-site request to reuse.
- Status: accepted for the local demo; reassess with firm SSO/session design.

### Content-bearing framework logs disabled

- Category: logging and privacy
- Severity: informational
- Confidence: high
- Evidence: Uvicorn access/error and SQL logs are disabled; allowlisted application events and
  durable audit/failure states remain.
- Rationale: raw request/exception/database logs could expose future restricted content or
  credentials. Correlation IDs and deterministic reproduction are the supported diagnostic path.
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
