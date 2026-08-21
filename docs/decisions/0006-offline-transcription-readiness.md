# ADR 0006: Offline transcription readiness before any live provider use

- Status: accepted for Slice 3A
- Decision date: 2026-08-17
- Official documentation accessed: 2026-08-17

## Context

The firm-owned AI project, approved provider terms and account data controls, authorization
reference, and approved credentials do not exist. Live transcription is therefore unavailable.
The next safe increment is a production-shaped boundary validated only with locally generated
non-human media and an injected, network-blocked mock transport.

Official OpenAI documentation accessed on 2026-08-17 states:

- completed or bounded recordings use file transcription through `/v1/audio/transcriptions`;
- supported file inputs are `mp3`, `mp4`, `mpeg`, `mpga`, `m4a`, `wav`, and `webm`, up to 25 MB;
- ordinary original-language transcription starts with `gpt-transcribe`;
- speaker-labeled transcription uses `gpt-4o-transcribe-diarize` with
  `response_format="diarized_json"`;
- audio longer than 30 seconds requires `chunking_strategy="auto"` or a configured voice-activity
  strategy;
- the current model page exposes `gpt-4o-transcribe-diarize` as an alias without a dated stable
  snapshot, which creates model-drift risk;
- the current data-control table lists `/v1/audio/transcriptions` with no abuse-monitoring or
  application-state retention and as eligible for Zero Data Retention.

Sources:

- https://developers.openai.com/api/docs/guides/speech-to-text
- https://developers.openai.com/api/docs/models/gpt-4o-transcribe-diarize
- https://developers.openai.com/api/docs/guides/your-data

Model availability, request fields, limits, retention behavior, regional behavior, and account
controls are time-sensitive. Documentation is not proof of the actual firm account. Slice 3B must
renew these checks against the approved firm project before any live request.

## Decision

Slice 3A implements strict media and transcript contracts, local synthetic object storage,
content-based inspection, channel-preserving normalization, safe metadata persistence, and a
candidate OpenAI SDK adapter behind the accepted transcriber boundary. The SDK client and
transport are injected. Demo and test application factories never construct a provider client.

The candidate request uses `gpt-4o-transcribe-diarize`, `diarized_json`, and automatic chunking
only when duration exceeds 30 seconds. The fallback model identifier remains configurable.
Provider speaker labels are opaque diarization labels only and always map to an unverified
`unknown_participant`. Known-speaker names, references, voiceprints, biometric matching, and
speaker enrollment are prohibited even though the provider documentation describes optional
known-speaker references.

Text-only fallback preserves original-language text, marks timestamps and diarization
unavailable, creates no segments, and enters `requires_human_review`. It cannot support accepted
findings because evidence timestamps are unavailable.

OpenAI Python SDK `3.2.0` and Debian ffmpeg `7:5.1.9-0+deb12u1` are exact pins. ffprobe and ffmpeg
are invoked with fixed argument lists, timeouts, no shell, restrictive object permissions, and
paths previously confined to the synthetic temporary root.

## Hard stop

`LIVE_TRANSCRIPTION_ENABLED=false`, `LIVE_TRANSCRIPTION_AUTHORIZED=false`, and an empty
`TRANSCRIPTION_APPROVAL_REFERENCE` are mandatory. Slice 3A rejects live construction regardless
of an ambient API key. Full Slice 3 and CL-060 remain incomplete. Slice 3B requires separate
authorization for the firm project, provider/account, terms and controls, credential handling,
generated test set, and an exact live-test reference. Real client media remains prohibited.
