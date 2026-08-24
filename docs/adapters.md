# Adapter boundaries

## Local OpenAI CLI development transport

`openai_cli_local` is available only under the synthetic `local_dev` profile. The repository
declares exact support for OpenAI CLI `1.6.0` and local contract
`openai-cli-audio-transcriptions-v1`. Preflight checks the installed version and
`audio:transcriptions create` command surface without passing credentials or making a request.
Missing, legacy, mismatched, or unsupported capability selects the fixture and transcript-only
fallback.

The CLI client is an SDK-shaped shim, so successful provider JSON passes through the same strict
OpenAI response converter, opaque-speaker mapping, error classifier, and three-attempt cap as the
SDK adapter. It supports only `gpt-4o-transcribe-diarize`, `diarized_json`, the source
language hint, and automatic chunking above 30 seconds. Safe provenance records the transport,
declared contract, observed version or `unavailable`, model, response format, input SHA-256
fingerprint, attempt, and result kind; it never records command text, environment values,
absolute media paths, stdout/stderr, transcript content, or credentials.

The only real process implementation uses direct argument-array execution with no shell. It
requires an allowlisted resolved executable, builds a restricted child environment, accepts only
explicit approved OpenAI environment names, caps output, and terminates the whole process group on
timeout or cancellation. Normal unit tests inject a fake runner and never spawn a process. A
separate Docker `--network none` harness exercises the real boundary against the deterministic
repository fake.

The transcript-only adapter consumes one invented, strict artifact that embeds the existing
`IngestionEvent` and `Transcript` contracts. There is no second transcript schema and no media
object. Invalid, oversized, symlinked, or group/world-writable inputs are rejected before database
mutation. Valid import uses existing analysis, report, evidence, feedback, audit, and persistence
contracts; deterministic IDs make duplicate import a no-op.

## Local request adapters

The demo API adds only a request adapter around existing local components. Multipart audio is
bounded before buffering, parsed as exactly one file, inspected by content, and admitted only when
its SHA-256 fingerprint exists in the private generated-input allowlist. It then uses the accepted
local object store, media normalizer, fixture transcriber, fixture analyzer, and report repository.
The JSON mode passes the complete bounded body to the existing transcript-only parser and importer;
it creates no object and never invokes a transcriber. Neither mode constructs an OpenAI client or
CLI process.

## Bounded OpenAI live verification

The candidate OpenAI file-transcription adapter has a gated `live_test` factory. The
factory revalidates every owner gate before client construction, sets SDK retries to
zero, refuses redirects and arbitrary endpoints, and uses an injected shared request
guard. Live requests use only `/v1/audio/transcriptions`,
`gpt-4o-transcribe-diarize`, and `diarized_json`; longer media uses automatic chunking.
Provider speaker labels remain opaque and map only to `unknown_participant`.

These are architecture seams. Slices 1 and 2 implement local deterministic fixture adapters.
The disabled candidate file-transcription adapter is exercised only through an injected
mock transport. No vendor credential, live provider URL, or external request is implemented.

| Boundary | Synthetic/test option | Future option | Current state |
|---|---|---|---|
| `CallSource` | `FixtureCallSource`; local synthetic manual upload | Broadvoice only after approval | Deterministic generic ingestion events plus a narrow local route |
| `Transcriber` | `FixtureTranscriber`; offline `OpenAITranscriber`; local `openai_cli_local` shim | Separately authorized approved provider adapter | Exact fixtures, network-blocked response contracts, and bounded local CLI process harness |
| `Analyzer` | `FixtureAnalyzer` | Approved structured analyzer | Exact facts-first fixture responses; no keyword engine |
| `ObjectStore` | `LocalSyntheticObjectStore` | `PrivateCloudObjectStore` | No object content stored; deployment requires private cloud setting |
| `Notifier` | `NoOpNotifier` | `SecureReportReadyNotifier` | No-op setting only; no message or delivery code |

Future call sources must normalize at the boundary before domain processing. The core pipeline
must never receive provider credentials or provider URLs. A notification may eventually state
only that a secure report is ready; it must contain no call information.

Broadvoice is explicitly unimplemented and disabled. Account-specific documentation and test
access are required before even a synthetic field shape is created. There is no anonymous
webhook route.

The candidate sends file transcription to `/v1/audio/transcriptions` with configurable model
identifiers, `diarized_json`, and automatic chunking above 30 seconds. It never uses the Files API,
Realtime API, streaming, known-speaker names/references, or analysis/report generation. Provider
speaker labels remain opaque and map only to unverified unknown participants. Normal demo/test
application factories construct no network client, and live construction remains behind the
explicit owner-gated hard stop.
