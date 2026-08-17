# Adapter boundaries

These are architecture seams. Slice 1 implements only local deterministic fixture adapters. No
vendor header, signature rule, credential, provider URL, external retry assumption, or network
request is implemented.

| Boundary | Synthetic/test option | Future option | Slice 1 state |
|---|---|---|---|
| `CallSource` | `FixtureCallSource` | Manual upload; Broadvoice only after approval | Deterministic generic ingestion events; no route |
| `Transcriber` | `FixtureTranscriber` | Approved provider adapter | Exact fixture responses and named synthetic failures |
| `Analyzer` | `FixtureAnalyzer` | Approved structured analyzer | Exact facts-first fixture responses; no keyword engine |
| `ObjectStore` | `LocalSyntheticObjectStore` | `PrivateCloudObjectStore` | No object content stored; deployment requires private cloud setting |
| `Notifier` | `NoOpNotifier` | `SecureReportReadyNotifier` | No-op setting only; no message or delivery code |

Future call sources must normalize at the boundary before domain processing. The core pipeline
must never receive provider credentials or provider URLs. A notification may eventually state
only that a secure report is ready; it must contain no call information.

Broadvoice is explicitly unimplemented and disabled. Account-specific documentation and test
access are required before even a synthetic field shape is created. There is no anonymous
webhook route.
