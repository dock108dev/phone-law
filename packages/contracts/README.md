# Shared contracts

Slice 1 adds strict frozen Pydantic contracts for normalized calls, ingestion, transcripts,
facts, findings, evidence, analyses, provenance, attempts, sanitized failures, and the synthetic
draft playbook. Undeclared fields are rejected. Canonical generated schemas live in `schemas/`
and `scripts/generate_contract_schemas.py --check` prevents model/schema drift.

Report contracts remain outside this slice.
