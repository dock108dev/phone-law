# ADR 0008: local CLI development bridge

- Status: implemented for offline acceptance
- Authorization: owner direction in chat on 2026-08-17
- Documentation refreshed: 2026-08-17

## Decision

Slice 3C adds `local_dev` as a synthetic-only command-line profile and
`openai_cli_local` as an explicit operator transport. The API, worker, browser, demo,
test, `live_test`, staging, and production application factories do not acquire a host
CLI dependency.

The declared contract is OpenAI CLI `1.6.0`,
`openai-cli-audio-transcriptions-v1`, and the resource command
`audio:transcriptions create`. The request surface is restricted to
`gpt-4o-transcribe-diarize`, `diarized_json`, a source language hint, and automatic
chunking above 30 seconds. Root help and transcription-subcommand help are checked
separately because response-output `--format` is a global flag. An absent, legacy,
mismatched, or changed CLI fails closed to fixture and transcript-only development.
The bridge does not install or upgrade the host tool.

The [official CLI repository](https://github.com/openai/openai-cli) documents the
resource-based command structure, named credential environment variables, file
arguments, and the sensitivity of debug output. The
[official `1.6.0` release](https://github.com/openai/openai-cli/releases/tag/v1.6.0)
is the accepted public version declaration. The
[speech-to-text guide](https://developers.openai.com/api/docs/guides/speech-to-text)
documents the transcription endpoint, diarized JSON, and automatic chunking.

## Process and data boundary

One injected runner owns all process execution. The production-shaped runner uses an
absolute allowlisted executable, direct argument arrays with no shell, a rebuilt child
environment, named environment-variable admission, private temporary input, bounded
stdout/stderr, wall-clock timeout, cancellation, and process-group termination. It
returns only typed content-free failures and confirms cleanup. Normal unit tests use a
fake runner and spawn no process; a separate network-blocked harness exercises the real
runner against a deterministic fake executable.

Successful CLI JSON passes through the existing SDK adapter's strict response
converter, speaker normalization, retry classification, and transcript contract. Safe
provenance contains only the transport, declared contract, observed version or
`unavailable`, model, response format, input fingerprint, attempt number, and
deterministic-or-live result kind. Commands, absolute media paths, environment values,
credentials, project identifiers, raw stdout/stderr, provider payloads, and transcript
content are prohibited from operational metadata.

## Transcript-only fallback

The fallback imports a strict invented artifact composed from the existing ingestion
and transcript contracts; it does not introduce a second transcript schema. The entire
bounded private file is validated before the first database write. Valid input reuses
the existing immutable processing, analysis, daily-report, evidence, reviewer-feedback,
audit, and persistence contracts. It stores no media reference and uses deterministic
identifiers so duplicate delivery is idempotent.

## Consequences and stop boundary

No schema migration is required because the new source mode and safe provenance fit the
existing JSON contract columns. Slice 3C unblocks later local synthetic and
transcript-only implementation only. It does not complete Slice 3B or CL-060, authorize
real or human audio, establish a firm project or its data controls, or authorize a live
CLI/SDK request. Any future generated-audio CLI probe must independently reuse every
Slice 3B authorization, request, retry, duration, byte, cost, data-control, and cleanup
gate.
