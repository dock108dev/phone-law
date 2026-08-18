# Local development and troubleshooting

Run `make bootstrap`, `make dev`, then `make smoke`. Stop with `make stop`; this preserves the
local synthetic database. Restart with `make dev`.

If a port is occupied, stop the conflicting local process or update only the host-side loopback
mapping. Do not publish services on all interfaces. If API or worker readiness fails, confirm
PostgreSQL is healthy and rerun `docker compose run --rm api alembic upgrade head`.

If a clean reset is necessary, `CONFIRM_LOCAL_DATA_DELETE=yes make clean` removes only Compose
resources named `colacci-law`, including its synthetic database volume. Then rerun bootstrap.

If a locked package changes, update the exact direct version first and mechanically regenerate
the relevant lock; run every stable command plus the separate advisory audit. Do not hand-edit a
resolved lockfile.

Tests, smoke checks, and migrations use no live AI, telephony, email, cloud, or identity service.
No external credential is accepted.

## Slice 3C CLI and transcript-only workflow

Run the capability check first:

```bash
make transcription-cli-preflight
```

It makes no provider request, does not inspect or print credential values, and writes a sanitized
report to `/tmp/colacci-law-slice3c/evidence/cli-preflight.json`. Supported means exact CLI
`1.6.0` plus the declared `audio:transcriptions create` surface. Any other result selects
`fixture-and-transcript-only`; do not upgrade the host as part of this slice.

Run the entire offline acceptance path:

```bash
make test-transcription-cli-offline
```

This runs injected CLI contracts and a dedicated child-process security harness with external
networking disabled, then imports the invented transcript-only fixture on the internal database
network. It validates the full report/evidence/feedback loop, invalid-input rollback, duplicate
idempotency, content-free evidence, and cleanup. Evidence is generated only under
`/tmp/colacci-law-slice3c/evidence/` and is not committed.

Do not place human or realistic audio, a credential, a project identifier, transcript text, raw
CLI output, or a command string in evidence. The Slice 3B command `make test-transcription-live`
remains separately owner-gated and is not a fallback or completion requirement for Slice 3C.
