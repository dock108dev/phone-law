# ADR 0007: bounded live generated-audio transcription

- Status: implemented; final re-entry preflight blocked before client construction
- Preflight authorization: `OWNER-CHAT-2026-08-19-SLICE-3B-REENTRY-PREFLIGHT-ONLY`
- Documentation refreshed: 2026-08-19 22:09:45 EDT

## Decision

Slice 3B adds a `live_test` profile that is separate from demo, test, staging, and
production. It permits only three freshly generated non-human assets and only the
OpenAI file-transcription endpoint with `gpt-4o-transcribe-diarize`,
`diarized_json`, and automatic chunking for media over 30 seconds. Analysis,
notifications, manual upload, Broadvoice, Files API, realtime, fallback models,
known-speaker references, real data, and human recordings remain disabled.

The global endpoint class is the default (`api.openai.com`). An approved official
regional hostname may be configured explicitly, but arbitrary hosts, redirects,
credentials in URLs, query strings, and fragments are rejected. This generated-audio
authorization does not approve any endpoint for later client data.

The zero-request preflight must pass before the one-shot live command can construct a
client. The live command additionally requires explicit execution confirmation. A
shared guard reserves every attempted upload before dispatch and enforces four total
requests, one transient retry, 120 cumulative audio seconds, 20 MiB cumulative media,
and a $1 application-side budget. Authentication, permission, invalid-request, and
malformed-response failures are not retried.

## Documentation refresh

The [file-transcription guide](https://developers.openai.com/api/docs/guides/speech-to-text)
documents the `/v1/audio/transcriptions` endpoint, a 25 MB file limit, supported file
types, `diarized_json`, speaker/timestamp segments, and automatic chunking for longer
inputs. The [model page](https://developers.openai.com/api/docs/models/gpt-4o-transcribe-diarize)
confirms that the diarization model is available through the transcription endpoint;
the undated model alias remains a drift risk. The [data-controls guide](https://developers.openai.com/api/docs/guides/your-data)
currently lists transcription requests as not used for training, with no abuse-retention
or application-state retention, and as Zero Data Retention eligible. Zero Data Retention
and Modified Abuse Monitoring are account/project controls that require approval; public
documentation does not prove the firm account's configuration.

The 2026-08-19 official refresh confirms that `diarized_json` returns speaker, start,
and end segments and that `chunking_strategy=auto` is required for this model when an
input exceeds 30 seconds. The API guide continues to list a 25 MB file limit and
`mp3`, `mp4`, `mpeg`, `mpga`, `m4a`, `wav`, and `webm` inputs. The model page lists
$2.50 per million audio input tokens and $10.00 per million output tokens; it does not
publish a separate per-minute estimate for the diarization model. Free tier is not
supported, while tier-specific rate limits are public but actual firm account access
remains unverified.

The final re-entry preflight requires a named firm-owned project, approved account and
project ownership, presence of an ephemeral project-scoped credential and project
identifier, confirmed project data controls, approved provider terms and intended
generated-audio test, and a new live-execution authorization identifier. Sensitive
runtime values are never read, validated, printed, hashed, or retained; only variable
presence is observed. The preflight authorization is not live-execution authority.
When any input is absent, the preflight blocks with zero client construction, requests,
retries, uploads, or cost and removes every generated or disposable artifact while
retaining only the sanitized report.

## Persistence and evidence

The live runner uses a disposable SQLite database only during the bounded process,
exports approved synthetic transcript and evaluation evidence outside the repository,
then removes the database and all temporary media. No migration is required. Operational
logs contain only case codes and terminal states; transcript content is restricted to
the designated external evidence file.
