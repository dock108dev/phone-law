# ADR 0001: Pinned local application stack

**Status:** Accepted for Slice 0

Use FastAPI/Python for API and worker boundaries, React/TypeScript for the web shell, PostgreSQL
with Alembic for state, Docker Compose for local orchestration, and Make as the stable operator
surface. Pin runtime patches, exact direct dependencies, complete locks, and hashes.

This supports one reproducible local path without cloud or queue infrastructure. Container image
digests remain a later supply-chain decision because local CPU platforms differ.
