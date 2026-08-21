# Data classification

| Class | Examples | Slice 2 handling |
|---|---|---|
| Restricted client content | Real audio, transcript text, caller/staff identity, phone number, matter facts | Prohibited; local routes accept only allowlisted generated audio or the strict invented artifact |
| Restricted credentials | Authorization headers, API keys, database/provider credentials, signed URLs | Never logged or committed; local demo credential is explicitly non-deployable |
| Confidential review data | Findings, evidence, reviewer feedback, playbook, reports | Synthetic-only, role-gated, no-store responses; immutable or append-only database records |
| Internal operational metadata | Service, profile, status, version, safe route, correlation ID, duration, error code | Allowlisted structured logging only |
| Public documentation | Architecture and synthetic-only operating instructions | Repository documentation |

Correlation IDs must be generated opaque values and cannot contain content. Database URLs are
passed only into the driver boundary. Query strings, headers, exception messages, and payloads
are excluded from logs.

The `fixtures/` folder contains only explicit fictional scenarios and a synthetic playbook. No
recording, real client identity, phone number, credential, or live-service payload is included.
Generated non-human upload inputs exist only beneath the disposable Slice 4 `/tmp` root and are
deleted after tests. Receipt metadata is internal operational data: opaque IDs, a truncated hash
reference, bounded language/direction/time, synthetic extension, authenticated demo principal,
state, attempt, safe versions, and lifecycle timestamps. Original filenames, paths, MIME headers,
transcript text, and request bodies are prohibited from receipt persistence.
