# Local development and troubleshooting

Docker, Compose, `make`, a POSIX shell, and host `python3` are required. Host Python runs only
deterministic fixture/evidence helpers; application code and dependencies run in the Python 3.13.5
container. Host Node is not required.

Run the first-day workflow from the repository root:

```bash
make bootstrap
make dev
make smoke
make seed-demo-month
```

Open `http://localhost:15173`. Stop with `make stop`; this preserves the local synthetic database.
Restart with `make dev`.

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

## Routine validation

The complete command, isolation, and evidence matrix is in [Testing](../testing.md).

Run these after ordinary source or documentation changes:

```bash
make lint
make typecheck
make test
make test-integration
```

Use `make smoke` after route, runtime, configuration, migration, or container changes. Run the
affected browser gate for review, upload, or operations changes: `make test-e2e`,
`make test-manual-upload`, or `make test-local-operations`. The focused scripts create disposable
Compose projects, inspect sanitized logs, and clean up their isolated resources.

`make audit` is a separately labeled online vulnerability-advisory check. It is not part of the
deterministic offline suite and does not replace exact dependency pins.

## Local CLI and transcript-only workflow

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
CLI output, or a command string in evidence. The `make test-transcription-live` command remains
separately owner-gated and is not a fallback or routine completion requirement.

## Local synthetic manual upload

Run the complete isolated proof before using the page:

```bash
make test-manual-upload
```

The command creates only deterministic non-human tones and one invented transcript artifact,
runs request/media/transcript/lifecycle failures on an internal-only network, then drives the
administrator, operations, and reviewer browser loop. Sanitized JSON, logs, diagnostics, and
redacted screenshots are retained under `/tmp/colacci-law-slice4-local/evidence/`; generated
inputs and temporary objects are removed. A successful run ends with zero temporary media and zero
CLI, SDK, or provider requests.

For local interaction, run `make dev`, open `/uploads`, select Demo admin or Demo operations, and
choose exactly one artifact created by `scripts/generate_manual_upload_assets.py`. Never choose a
human recording or a real transcript. Check the generated-only attestation, use only `SYN-000`
through `SYN-999`, and submit. A ready audio receipt may be cancelled before its short local
processing delay; a retry button appears only for a named retryable failure. Completed receipts
link to the immutable call and daily report. Demo operations cannot append feedback; switch to Demo
reviewer for the review step.

If a receipt reaches `deletion_failed`, stop. Do not retry by manually manipulating the object or
database. Preserve only the content-free receipt/evidence, run the focused test to diagnose the
local boundary. Use the Operations page for policy-driven synthetic retention only; it is
not an approved production retention policy.

## Local operations

Run `make test-local-operations` before using the Operations page. The focused proof is
network-isolated, uses an injected clock, covers every demo role and adversarial session case,
executes deletion success/retry/terminal/restart cases, runs the disposable restore drill, checks
responsive accessibility, inspects content-free logs, and removes its stack and runtime. Private
evidence remains under `/tmp/colacci-law-slice5a/evidence`. Follow the complete
[operator and incident runbook](../local-operations.md).
