# Adapter boundaries

These are architecture seams, not Slice 0 integrations. No call-shaped payload, vendor header,
signature rule, credential, provider URL, retry schedule, or external request is implemented.

| Boundary | Synthetic/test option | Future option | Slice 0 state |
|---|---|---|---|
| `CallSource` | `FixtureCallSource` | `ManualUploadCallSource`; `BroadvoiceCallSourcePlaceholder` | Configuration name only; no call contract or route |
| `Transcriber` | `FixtureTranscriber` | Approved provider adapter | Configuration name only; disabled in deployment profiles |
| `Analyzer` | `FixtureAnalyzer` | Approved structured analyzer | Configuration name only; disabled in deployment profiles |
| `ObjectStore` | `LocalSyntheticObjectStore` | `PrivateCloudObjectStore` | No object content stored; deployment requires private cloud setting |
| `Notifier` | `NoOpNotifier` | `SecureReportReadyNotifier` | No-op setting only; no message or delivery code |

Future call sources must normalize at the boundary before domain processing. The core pipeline
must never receive provider credentials or provider URLs. A notification may eventually state
only that a secure report is ready; it must contain no call information.

Broadvoice is explicitly unimplemented and disabled. Account-specific documentation and test
access are required before even a synthetic field shape is created. There is no anonymous
webhook route.
