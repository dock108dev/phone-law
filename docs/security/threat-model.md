# Initial threat model

## Assets and trust boundaries

Restricted assets include synthetic transcripts, caller/staff metadata, findings, reviewer
feedback, and audit history. Slice 2 stores only deterministic fictional fixtures and synthetic
human-review records. Current boundaries are browser-to-web/API, API/worker-to-PostgreSQL,
environment configuration, container images, logs, and the source repository.

## Threats and Slice 2 controls

| Threat | Control now | Remaining requirement |
|---|---|---|
| Real data enters demo/test accidentally | Profiles reject real-data switches; explicit prohibition and attestation; only private generated fingerprints or a strict invented artifact pass | Authenticated approved real-data ingestion in a later slice |
| Unsafe deployment uses demo controls | Staging/production startup rejects fake auth, local storage, fixtures, weak secrets, absent retention, debug, permissive CORS, and local DB | Firm-owned SSO, private storage, secrets, region, and approvals |
| Sensitive request or error data reaches logs | Access logs off; bodies ignored; allowlisted logger; opaque errors; browser suite scans application logs for fixture/review content, credentials, and URLs | Central logging access/retention decision |
| Secret enters source | Ignore rules, deterministic scanner, high-signal scanner test, review | Managed secret store and rotation runbook |
| Schema is missing or stale | API/worker readiness requires exact migration revision | Safe deployment migration procedure |
| Dependency compromise or drift | Exact direct/transitive locks, hashes, image patch tags, offline pin checks, separate advisory audit | Digest/signature policy and routine advisory review |
| Browser mislabels synthetic content | Persistent top banner, synthetic references, advisory notices, locked real-data configuration | Separate staging/real visual treatment before use |
| Reviewer feedback overwrites model output | Accepted analyses, report versions, review events, and audit events are database-immutable; feedback is appended | Firm identity and retention policy before real use |
| Privileged operations are exposed | Allowlisted demo principals; reviewer/operations/admin role checks; denied writes create content-free audit records | Firm SSO and centralized authorization before staging |
| Playbook publication changes prior analysis | Playbook structured payload is immutable; only lifecycle timestamps/status can change; analyses retain original provenance | Approved authoring and change-control process |
| Broadvoice contract is guessed | No route, fields, header, signature, URL, fixture, or code | Account-specific feasibility evidence |
| Overbroad network exposure | Every published local port binds to loopback | TLS, firewall, private networking, and approved ingress in staging |
| Host-header or browser embedding abuse | API allowlists trusted hosts; API and local web set no-store, noindex, nosniff, deny framing, strict referrer/permissions, resource isolation, and CSP headers; API also sets opener isolation | Approved HTTPS proxy must preserve/strengthen headers and add web opener isolation/HSTS only after TLS is enforced |
| Denial of service | Local synthetic-only routes, bounded fixture corpus, no ingestion | Rate limits and resource limits before ingestion |
| CLI argument injection or shell expansion | Direct argument array, `shell=False`, fixed option surface, absolute allowlisted executable | Reassess before any broader command surface |
| Ambient environment or credential leakage | Rebuilt child environment, named-variable allowlist, no value logging, no command logging | Managed ephemeral credential delivery before any separately authorized live run |
| Child hangs, floods output, or leaves descendants | Wall-clock timeout, output cap, cancellation, process-group termination, private temporary input, cleanup confirmation | Provider-specific operational limits before production |
| Unsupported CLI changes response semantics | Exact version and command-surface preflight; fail closed to offline fallback | Re-accept every declared CLI contract change |
| Transcript-only artifact bypasses validation | Regular private bounded file, strict existing contracts, full validation before first database write, deterministic idempotency | Authenticated approved ingestion before real data |
| Upload bypasses authenticated role | Principal is resolved before buffering/allocation; request role fields are rejected; reviewer denials are audited | Firm SSO and centralized policy before staging |
| Filename or multipart input escapes local storage | Single file, strict safe name, no destination field, no path import, opaque object ID, fixed `/tmp` root, no symlinks | Private cloud object boundary before real use |
| Duplicate or retry creates competing records | Unique submission/content/source IDs; row locks; retry increments attempt on the same call | Distributed idempotency design before external ingestion |
| Temporary media survives its lifecycle | Cleanup on validation failure, terminal result, success, cancellation, and unexpected exception; deletion failure is visible and audited | Approved retention/deletion policy belongs to Slice 5 |

## Abuse cases checked

- A caller-like value in a query string or authorization header is not logged.
- An arbitrary or content-bearing correlation ID is replaced.
- A database failure returns only `not_ready` and an internal code.
- An unsafe production process exits with code 78 without echoing configuration values.
- A migration test refuses to downgrade any database whose name does not end in `_test`.
- A permanent failure cannot be retried and a reviewer cannot open the operations queue.
- A reviewer cannot publish a playbook; an administrator can publish only an existing draft.
- Evidence links move keyboard focus to the cited original-language segment.
- CLI timeout, cancellation, oversized output, missing executable, and nonzero exits return only
  typed content-free failures and leave no temporary media.
- Malformed, unsupported, oversized, or unsafe transcript-only artifacts leave database counts
  unchanged.
- Missing attestation, empty or invalid multipart, unsupported/corrupt/overlong media, unsafe name,
  and invalid language/direction/time leave no receipt or temporary object.
- Object-store, database, unexpected-processing, cancellation-race, and deletion failures return
  content-free named outcomes; the focused suite confirms no test orphan remains.
- An untrusted HTTP `Host` is rejected before route execution, and API/web responses carry the
  documented defensive header set.

## Stop conditions

Any real or realistic call content, live credential, unapproved provider call, guessed Broadvoice
contract, permissive production guard, or content-bearing log is a release blocker.
