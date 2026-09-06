# Local development and troubleshooting

Docker, Compose, `make`, a POSIX shell, and host `python3` are required. Host Python runs only
deterministic fixture/evidence helpers; application code and dependencies run in the Python 3.14.7
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

## Isolated desktop-browser review rehearsal

Use this supported launch path for the revised morning experience. It leaves any
retained `colacci-law` owner session untouched. Run from the original repository:

```bash
python3 scripts/local_review.py start
python3 scripts/local_review.py seed
```

Open **http://127.0.0.1:15176** in the host desktop browser. Expect dataset
`demo-month-2026-07-v2`, simulated morning July 16, reviewing July 15 in
America/New_York: ten calls and three attention calls. The seed is 20260702 and
materializer is `authored-month-schedule-v2`. This is engineering rehearsal,
not owner acceptance. Use the Desktop tracker for current status.

The launcher uses only project `colacci-law-slice7c`, its own database volume,
and owner-controlled private `/tmp/colacci-law-slice7c-runtime`. It refuses an
occupied port or an existing relay. Build steps fetch pinned dependencies; running
product services use internal Docker networks, with no container ports published.
A host Python TCP relay binds only 127.0.0.1:15176 and forwards bytes through Docker
stdio to the web container's fixed 127.0.0.1:5173 endpoint. It supports HTTP and Vite
WebSockets without adding a gateway network, exposing the Docker socket inside
containers, allowing proxy destinations, or granting product egress. API requests
use the existing same-origin web proxy. Host Python uses only its standard library.
Do not manually attach any service to a non-internal network.

```bash
python3 scripts/local_review.py restart  # preserves saved reviews and database
python3 scripts/local_review.py stop     # stops relay and stack; retains database
python3 scripts/local_review.py start    # supported restart after stop
python3 scripts/local_review.py seed     # idempotent; preserves review events
python3 scripts/local_review.py clean    # removes only this disposable stack/volume
```

Keep evidence outside the runtime. `clean` retains private runtime files (including
relay diagnostics) for inspection; remove only this attempt's files after preserving
needed evidence. It never deletes owner resources or historical evidence. A failed
relay start/stop is an error, not a successful launch: retain `relay.log`, inspect
`relay.ready`, and do not delete the marker or improvise a network connection.

For independent gates, export `COMPOSE_PROJECT_NAME=colacci-law-slice7c`,
`COMPOSE_FILE=docker-compose.yml:infrastructure/local/slice7c-compose.yml`,
`SLICE4_RUNTIME_ROOT=/tmp/colacci-law-slice7c-runtime`,
`COLACCI_FIXTURE_NETWORK=colacci-law-slice7c_fixture`, and
`COLACCI_FIXTURE_IMAGE=colacci-law-slice7c-api`, and
`COLACCI_FIXTURE_REPORT_ROOT=/tmp/colacci-law-<attempt>/evidence/fixtures`. Supply a fresh evidence directory
through each gate's `SLICE6C_EVIDENCE_DIR`, `SLICE6D_EVIDENCE_DIR`,
`SLICE4_EVIDENCE_DIR`, or `SLICE5A_EVIDENCE_DIR` parameter. Local Operations also
accepts `SLICE5A_RUNTIME_ROOT=/tmp/colacci-law-<attempt>/runtime`.
E2E no longer stops or restores its caller's stack. Its separate technical retry
probe begins in an empty database, preserves a permanent failure, simulates an
interrupted retryable call, and retains one expected missing call. It is separate
from both the ordinary v2 month and the exhaustive acceptance fixtures.

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
CLI output, or a command string in evidence. Provider execution is unsupported; the retired factory always rejects construction.

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

### Disposable qualification resources

Use fresh attempt paths for release, acceptance, UI, month, E2E, manual-upload,
and operations gates. These entry points refuse existing evidence/runtime paths
and existing project containers (including stopped ones), volumes or networks
before enabling cleanup. Their ownership marker authorizes cleanup only for that
invocation. Cleanup retains evidence and cached images. Preserve a failed attempt;
choose new paths for a later invocation. Never pass retained owner runtime
`/tmp/colacci-law-slice4-local` to a qualification gate.

The release gate accepts `COMPOSE_PROJECT_NAME`, `SLICE4_RUNTIME_ROOT` and
`SLICE6C_EVIDENCE_DIR`. It enforces the unpublished internal Slice 7C Compose
configuration, builds/verifies images named for that project, and retains image
proof under `candidate/`. The standalone month gate uses those same isolation
settings and requires its project images to be prepared beforehand.

Acceptance accepts `COLACCI_ACCEPTANCE_PROJECT`, `COLACCI_ACCEPTANCE_ROOT` and
`SLICE4_RUNTIME_ROOT`. `COLACCI_CANDIDATE_IMAGE_PREFIX` selects the previously
verified candidate images; all four are checked before being tagged for the
acceptance project. The collectors, cleanup writer and finalizer honor the same
`COLACCI_EVIDENCE_ROOT`. Each separate acceptance invocation needs its own root.
Its two internal technical rehearsals do not replace two required invocations.

Supporting gates accept these project/evidence settings, plus
`SLICE4_RUNTIME_ROOT` (operations uses `SLICE5A_RUNTIME_ROOT`):

| Gate | Project variable | Evidence variable |
| --- | --- | --- |
| UI | `COLACCI_UI_PROJECT` | `SLICE6D_EVIDENCE_DIR` |
| E2E | `COLACCI_E2E_PROJECT` | `SLICE4_EVIDENCE_DIR` |
| Manual upload | `COLACCI_MANUAL_PROJECT`, then `COLACCI_E2E_PROJECT` | `SLICE4_EVIDENCE_DIR`; browser evidence in `browser/` |
| Operations | `COLACCI_OPERATIONS_PROJECT` | `SLICE5A_EVIDENCE_DIR` |

For core Make targets, select a dedicated `COMPOSE_PROJECT_NAME` and
`COMPOSE_FILE=docker-compose.yml:infrastructure/local/slice7c-compose.yml` with a
fresh top-level `/tmp/colacci-law-...` `SLICE4_RUNTIME_ROOT`. Do not use bootstrap,
`make clean`, or the retained default stack to establish this boundary. Explicitly
inspect the selected project before startup and remove only that project's
resources afterward. Set `COLACCI_FIXTURE_IMAGE`, `COLACCI_FIXTURE_NETWORK`, and
`COLACCI_FIXTURE_REPORT_ROOT` for fixture evaluation and offline CLI execution.

`COLACCI_SYNTHETIC_ROOT` selects the host audio generator and audio/contract bind
mount; the container-side consumers retain `/tmp/colacci-law-slice3a`.
`COLACCI_CLI_ROOT` selects the host CLI preflight/inspection root and all three
CLI bind mounts; container-side consumers retain `/tmp/colacci-law-slice3c`.
Allocate these host roots freshly and preserve reports before reuse. These core
helpers do not claim ownership themselves. Never mount historical audio/CLI roots
into a new campaign. Fixture reports likewise use a private host mount with the
canonical container path. Container paths are not evidence of host path reuse.

The host launcher supports `COLACCI_REVIEW_PROJECT`, `COLACCI_REVIEW_RUNTIME` and
`COLACCI_REVIEW_PORT` for a separate disposable rehearsal. Use the same values for
`start`, `seed`, `restart`, `stop` and `clean`. Verify the chosen project/runtime is
unused and the loopback port is free before starting. `clean` removes that stack
and volume; archive its relay log before removing its private runtime directory.
Candidate build labels (`COLACCI_CANDIDATE_COMMIT`, `COLACCI_CANDIDATE_TREE`,
`COLACCI_RUNTIME_CONTRACT`) propagate through Compose builds, including the
launcher. Independently verify actual image IDs, runtimes and installed dependency
versions for each execution image; a label alone is not qualification.
