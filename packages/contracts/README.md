# Shared contracts

Strict frozen Pydantic models define normalized calls, ingestion, transcripts, facts, findings,
evidence, analyses, reports, feedback, upload receipts, operations, provenance, attempts,
sanitized failures, and synthetic playbooks. Undeclared fields are rejected.

Canonical generated schemas live in `schemas/`. Change the model first, regenerate with
`make generate-contract-schemas`, and use `make lint` to prevent model/schema drift.
