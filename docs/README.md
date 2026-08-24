# Documentation index

Use these documents for the current implemented repository. Historical design decisions live
under `decisions/`; current behavior is defined by source, tests, and the documents below.

## Develop and test

- [Local development and troubleshooting](runbooks/local-development.md): first setup, reset,
  validation matrix, and focused local workflows.
- [Testing](testing.md): core and focused gates, isolation, evidence, and CI mapping.
- [Architecture](architecture.md): runtime components and data flow.
- [Data model and migrations](data-models.md): persisted domains, migration history, and
  immutability rules.
- [Current implementation sources of truth](ssot.md): authoritative modules and known callers.
- [Maintainer guide](maintenance.md): change routing, large-file rationale, and cleanup standards.
- [Continuous integration](continuous-integration.md): required pull-request checks and local
  reproduction.
- [Technology choices](technology.md): pinned runtimes and dependency policy.
- [Configuration](configuration.md): profiles, environment settings, and fail-closed startup rules.
- [Adapter boundaries](adapters.md): supported synthetic inputs and gated transcription seams.

## Operate and diagnose

- [Local operations](local-operations.md): roles, reconciliation, retention, deletion, restore
  drills, and no-op notifications.
- [Error handling and incident diagnosis](runbooks/error-handling.md): safe failures, retry
  boundaries, and triage.
- [Staging and production safety](runbooks/staging-production-safety.md): non-local prerequisites;
  this is a guard description, not deployment authorization.
- [Security documentation](security/README.md): classification, threats, logs/secrets, and hardening.

## Decisions

ADRs under [decisions](decisions/) explain why durable boundaries were introduced. Slice labels in
ADRs are historical identifiers and must not be treated as current status. The only roadmap and
status source is `/Users/michaelfuscoletti/Desktop/colacci_law_next_steps.md`.
