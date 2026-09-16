# Security hardening — 2026-09-16

This source-only pass started at HEAD `0a791cddeaeda10abc85a0f8010ce901c3d46b3c`,
tree `6b75423c56e5cf9ede425c07b0d3162ab48a29d3`, with the existing September 16
error-handling work uncommitted. That work is preserved and has its own
[validation record](../runbooks/error-handling-validation-20260916.md).
These results cover uncommitted source, not a frozen candidate or release.

## Security understanding and scope

React/Vite serves the synthetic review UI and proxies requests to FastAPI;
PostgreSQL stores invented calls, reports, append-only feedback and audit records.
Published Compose ports bind to loopback. The worker serves health/readiness only;
there is no automatic queue consumer or scheduler. Browser-triggered upload,
retry, retention, configuration and restore-drill operations run explicitly.

All review/upload/operations routes depend on the allowlisted demo principal.
The shared role policy governs reviewer, operations and administrator permissions;
client role headers do not confer authority. This is intentionally selectable demo
identity, not a real session verifier. Non-demo/test review access fails closed.
There are no implemented SSO, password/reset/invite, multi-tenant, payment or
third-party callback surfaces. No cookie credentials are currently involved.

Reviewed request middleware, route dependencies and authorization, SQLAlchemy
query usage, strict upload parsing, generated fingerprint admission, local object
paths/permissions, frontend rendering/storage/request handling, settings,
logging, Compose/CI and host CLI process/transport code. SQL query parameters and
strict contracts remain in place; the inspected frontend renders React text and
stores demo selections/pending synthetic review intent, not provider credentials.
No new injection, cross-role access or secret-exposure exploit was established.
This targeted inspection is not an exhaustive penetration test.

Manual uploads cross an untrusted byte boundary with body limits, generated-only
fingerprint admission before native decoding, strict invented transcript validation,
private objects and explicit cleanup. Database access and mutations use repository
transactions and immutable records. API errors/logs exclude rejected input and raw
exception text. Host-only P1 tooling is separate: explicit admission, private
credential entry, bounded direct argv/environment, output/time limits, fixed TLS
tunnel and durable accounting. Source inspection did not access credentials,
private preparation, samples, ledgers or provider accounts, or execute the CLI.

## Confirmed vulnerabilities

No additional exploitable vulnerability was demonstrated in this bounded pass.
Previously implemented body limits, validation redaction, parser protocol limits
and safe errors remain; see the [earlier review](hardening-review.md). The new
origin check below is defense in depth, not a claim of an existing CSRF exploit.

## Implemented hardening finding

**SEC-007 — Explicit browser mutation origin admission**

- Category: browser-to-server request validation.
- Affected area: API middleware; every method except GET, HEAD and OPTIONS.
- Severity: low in the current loopback/synthetic threat model.
- Confidence: high.
- Why it matters: CORS controls browser response access/preflight behavior; it is
  not an application-side refusal of every disallowed-origin request.
- Realistic abuse scenario: if a future mutation accepts a simple browser request
  without the custom identity header, an unrelated site could submit it despite
  CORS response blocking. Current required demo headers already prevent ordinary
  cross-site forms from authenticating; no present cross-user compromise is claimed.
- Evidence: `app.py` previously installed CORSMiddleware and TrustedHostMiddleware
  but no mutation-origin admission; `demo_auth.py` requires a custom principal.
- Fix: `origin_boundary.py` rejects unknown, null, empty, malformed/nonmatching or
  duplicate Origin headers with sanitized 403 before body consumption or route
  effects. It admits an exact configured CORS origin or the request's same origin
  after trusted-host validation. The Vite proxy preserves Host/port. It does not
  derive trust from X-Forwarded-Host. Origin-less local clients retain normal auth.
  Safe headers, correlation IDs and content-free warning events are preserved.
- Status: fixed.

Origin is a browser defense, not authentication: native clients can omit or forge
it. No local session/token system was added. Read-only requests retain existing
CORS behavior. An HTTPS reverse proxy would require separately verified scheme,
Host and forwarding configuration; there is no supported hosted deployment here.

## Intentional acceptable patterns

- **Informational / high confidence / accepted locally — selectable identity.**
  `demo_auth.py` deliberately accepts fictional principal names, with server-side
  roles. Any local client can select an administrator. This is acceptable only
  for the existing synthetic loopback application; it is not production auth.
- **Informational / high confidence / accepted locally — HTTP and no CSRF cookie.**
  Compose uses loopback HTTP and no ambient session cookie. Keep HSTS absent until
  a separately approved HTTPS deployment; reassess CSRF with real sessions.
- **Informational / high confidence / accepted locally — development CSP.**
  Vite permits inline development scripts/styles and websocket connections.
  Production asset serving needs a stricter CSP and verified ingress headers.

## Deferred decisions and external verification

The sole prioritized roadmap is the Desktop tracker; this report does not authorize
implementation of its hosted/real-data phases. Retained findings are:

| Finding / category | Severity / confidence | Evidence and realistic consequence | Status and concrete path |
| --- | --- | --- | --- |
| Firm identity and authorization | High before deployment / high | No SSO/session verifier exists; exposing selectable demo identity would permit impersonation | Needs decision: D1 firm IdP, MFA, role mapping, revocation and session/CSRF policy, then negative authorization tests |
| Ingress and resource controls | High before shared ingestion / high | Body caps do not limit many concurrent or slow requests; no ingress quotas exist | Deferred to D1/D2: private TLS ingress, connection/read limits, concurrency quotas and parser isolation |
| Managed secrets and private storage | High before real data / high | Current local storage and demo DB credentials do not provide firm access isolation | Needs decision: managed secrets, least-privilege DB roles, encrypted storage, retention and backup ownership |
| Runtime and supply-chain evidence | Informational / high | Historical advisory results do not establish current package/image safety | Manual verification: authorized advisory/image scans and exact committed CI; no new package vulnerability claim |

Real TLS/IdP/network policy, key rotation, backup access, provider billing and OS
process-isolation properties require separate environment verification. None was
inferred from unit tests. No dependencies were changed; advisory services were
not contacted.

## Validation actually run

Used the existing `colacci-law-python-dependency-check:latest` image
(`sha256:a0395bbc2563e11aeebf98c81699d66327c6088ff3d85a55850f2c0f098fb2ff`),
Python 3.14.7, standalone disposable containers with `--network none`, current
source mounted read-only, no retained state mounts, and tool caches under `/tmp`.

- Ruff lint and format check: pass for `app.py`, `origin_boundary.py` and the new
  `tests/unit/test_mutation_origin.py`. An initial test formatting issue was fixed.
- `mypy apps/api/colacci_api/app.py apps/api/colacci_api/origin_boundary.py`: pass;
  this is the affected Python compile/type validation surface.
- Focused pytest: **110 passed, 2 skipped**. Files: `test_mutation_origin.py`,
  `test_security_boundaries.py`, `test_api_health.py`, `test_abend_handling.py`,
  `test_repository_error_boundaries.py`, all under `tests/unit/`.
  The skips are existing impossible repository outcome combinations.
- Dependency-pin verification: pass. Repository secret scan: pass, 468 files.
- Edited repository Markdown links and `git diff --check`: pass.
- New regressions cover POST/PUT/PATCH/DELETE, duplicate/null/unapproved origins,
  rejection before body/application access, safe logs/responses, same-origin
  proxy Host/port, configured origins, origin-less requests, unchanged principal
  requirements, Host rejection, health and CORS preflight.

No database integration, browser, live smoke/provider, full CI/security campaign,
packaging, signing or release validation ran. No frontend source changed. The
HTTP behavior was exercised in-process; actual browser/proxy operation was not
rerun. Preserve accepted demo and prepared probe identities; reconcile the changed
source through the bounded preparation workflow before fresh owner-local entry.
