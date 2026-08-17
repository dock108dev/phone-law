# Data classification

| Class | Examples | Slice 0 handling |
|---|---|---|
| Restricted client content | Audio, transcript text, caller/staff identity, full phone number, matter facts | Prohibited; no model, route, fixture, or storage location accepts it |
| Restricted credentials | Authorization headers, API keys, database/provider credentials, signed URLs | Never logged or committed; local demo credential is explicitly non-deployable |
| Confidential review data | Findings, evidence, reviewer feedback, playbook, reports | Not implemented; future private/authenticated/retained handling required |
| Internal operational metadata | Service, profile, status, version, safe route, correlation ID, duration, error code | Allowlisted structured logging only |
| Public documentation | Architecture and synthetic-only operating instructions | Repository documentation |

Correlation IDs must be generated opaque values and cannot contain content. Database URLs are
passed only into the driver boundary. Query strings, headers, exception messages, and payloads
are excluded from logs.

The `fixtures/` folders contain boundary notices only. Realistic call content is absent.
