# Environment profiles and configuration rules

## Slice 3C local-development profile

`local_dev` remains synthetic-only and rejects both live-transcription flags, an approval
reference, real data, non-local storage, real notifications, and non-fake authentication. Its
media root is fixed at `/tmp/colacci-law-slice3c/objects`. Only these adapter triples are valid:

- `fixture` / `fixture` / `fixture`
- `generated_synthetic` / `openai_cli_local` / `disabled`
- `transcript_only` / `transcript_only_import` / `fixture`

The local CLI transport is not selected by an ambient credential. Exact capability preflight is
required first; an unsupported result keeps the process on the fixture/transcript-only fallback.
The normal Compose services remain `demo`, and their application factories do not construct a
CLI client.

## Slice 3B live-test profile

`live_test` is a fail-closed, generated-media-only verification profile. It requires the
exact owner authorization, the approved transcription model, an explicit project-scoped
credential, official OpenAI endpoint selection, and the exact request, retry, duration,
byte, and application-budget caps. It disables analysis, notifications, real-data modes,
manual upload, and Broadvoice. The normal application and Compose defaults remain the
offline `demo` profile.

Use `make transcription-live-preflight` first. It runs without network access and emits
sanitized evidence under `/tmp/colacci-law-slice3b/reports`. Only a fresh passing report
allows `make test-transcription-live`, which also requires
`TRANSCRIPTION_LIVE_EXECUTION_CONFIRMED=true`. Credentials must arrive through an
approved ephemeral environment and must never be written to `.env` or repository files.
The account-specific data-control state must also be explicitly attested with
`OPENAI_PROJECT_DATA_CONTROLS_APPROVED=true`; credentials alone do not satisfy the gate.

| Profile | Purpose | Real data | Adapters | Storage/auth |
|---|---|---|---|---|
| `test` | Deterministic automated checks | Always rejected | Fixture adapters | Local synthetic/fake |
| `demo` | Default local application | Always rejected | Fixture adapters | Local synthetic/fake |
| `local_dev` | Bounded local CLI or transcript-only development | Always rejected | Exact allowlisted synthetic triples | Temporary local synthetic/fake |
| `live_test` | Owner-gated generated-audio verification | Always rejected | Gated file transcription; analysis disabled | Temporary local synthetic/project credential |
| `staging` | Future firm-owned preproduction | Disabled unless separately authorized | Fixture adapters rejected | Private cloud/SSO required |
| `production` | Future authorized deployment | Disabled unless separately authorized | Fixture adapters rejected | Private cloud/SSO required |

The default is `demo` and `ALLOW_REAL_CALL_DATA=false`. Slice 2 has no route capable of accepting
a call; its report and review routes read only committed synthetic fixtures and append synthetic
human-review events.

For `staging` or `production`, startup rejects:

- authentication other than `sso`;
- missing, short, demo, example, placeholder, local, or test secrets;
- storage other than `private_cloud`, or an example/missing bucket;
- fixture call source, transcriber, or analyzer;
- any call source except `disabled` or the future `manual_upload` boundary;
- any transcriber or analyzer other than `disabled` in this slice;
- unapproved or non-positive audio, transcript, analysis, or audit retention;
- debug mode;
- empty, wildcard, non-HTTPS, or localhost CORS origins;
- local, example, placeholder, or weak database configuration;
- real-call mode without both explicit authorization and a non-placeholder approval reference.

Real-call authorization is represented in validation so it can fail closed, but this does not
grant authority and does not make real processing available. The roadmap preflight remains a
separate stop condition.

Configuration values are never dumped or included in an exception log. Only the content-free
`unsafe_configuration` code is emitted when process startup is rejected.

## Normal profiles remain offline

- `LIVE_TRANSCRIPTION_ENABLED=false`
- `LIVE_TRANSCRIPTION_AUTHORIZED=false`
- `TRANSCRIPTION_APPROVAL_REFERENCE=`

These defaults remain enforced for `test`, `demo`, `staging`, and `production`; any live flag or
approval reference is rejected outside the exact `live_test` profile. An ambient API key is not
authority. Generated media is confined beneath an explicit `/tmp/colacci-law-*` root, the
application cap defaults to 20 MB and can never exceed the current documented 25 MB provider
ceiling, and the conservative synthetic duration cap is 60 seconds.
