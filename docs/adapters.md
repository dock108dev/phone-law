# Adapter boundaries

## Bounded OpenAI live verification

The candidate OpenAI file-transcription adapter has a gated `live_test` factory. The
factory revalidates every owner gate before client construction, sets SDK retries to
zero, refuses redirects and arbitrary endpoints, and uses an injected shared request
guard. Live requests use only `/v1/audio/transcriptions`,
`gpt-4o-transcribe-diarize`, and `diarized_json`; longer media uses automatic chunking.
Provider speaker labels remain opaque and map only to `unknown_participant`.

These are architecture seams. Slices 1 and 2 implement local deterministic fixture adapters.
Slice 3A adds a disabled candidate file-transcription adapter exercised only through an injected
mock transport. No vendor credential, live provider URL, or external request is implemented.

| Boundary | Synthetic/test option | Future option | Slice 1 state |
|---|---|---|---|
| `CallSource` | `FixtureCallSource` | Manual upload; Broadvoice only after approval | Deterministic generic ingestion events; no route |
| `Transcriber` | `FixtureTranscriber`; offline candidate `OpenAITranscriber` | Separately authorized approved provider adapter | Exact fixtures plus network-blocked response-contract and retry tests |
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
application factories construct no network client, and live construction always raises the
Slice 3B hard stop.
