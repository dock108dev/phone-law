# Initial threat model

## Assets and trust boundaries

Future restricted assets include recordings, transcripts, caller/staff metadata, findings,
reviewer feedback, credentials, and retention/audit history. Slice 0 holds none of those assets.
Current boundaries are the browser-to-web connection, health clients to API/worker, service to
PostgreSQL, environment configuration, container images, logs, and the source repository.

## Threats and Slice 0 controls

| Threat | Control now | Remaining requirement |
|---|---|---|
| Real data enters demo/test accidentally | Profiles always reject real-data switches; no ingestion route or call model | Authenticated approved ingestion in a later slice |
| Unsafe deployment uses demo controls | Staging/production startup rejects fake auth, local storage, fixtures, weak secrets, absent retention, debug, permissive CORS, and local DB | Firm-owned SSO, private storage, secrets, region, and approvals |
| Sensitive request or error data reaches logs | Access logs off; query/header bodies ignored; allowlisted logger; sanitized error codes | Central logging access/retention decision |
| Secret enters source | Ignore rules, deterministic scanner, high-signal scanner test, review | Managed secret store and rotation runbook |
| Schema is missing or stale | API/worker readiness requires exact migration revision | Safe deployment migration procedure |
| Dependency compromise or drift | Exact direct/transitive locks, hashes, image patch tags, offline pin checks, separate advisory audit | Digest/signature policy and routine advisory review |
| Browser mislabels synthetic content | Persistent top banner and locked real-data configuration | Separate staging/real visual treatment before use |
| Broadvoice contract is guessed | No route, fields, header, signature, URL, fixture, or code | Account-specific feasibility evidence |
| Overbroad network exposure | Every published local port binds to loopback | TLS, firewall, private networking, and approved ingress in staging |
| Denial of service | Only health routes exist; small responses and no request bodies | Rate limits and resource limits before ingestion |

## Abuse cases checked

- A caller-like value in a query string or authorization header is not logged.
- An arbitrary or content-bearing correlation ID is replaced.
- A database failure returns only `not_ready` and an internal code.
- An unsafe production process exits with code 78 without echoing configuration values.
- A migration test refuses to downgrade any database whose name does not end in `_test`.

## Stop conditions

Any real or realistic call content, live credential, unapproved provider call, guessed Broadvoice
contract, permissive production guard, or content-bearing log is a release blocker.
