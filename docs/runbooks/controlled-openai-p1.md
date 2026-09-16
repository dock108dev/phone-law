# Post-demo P1 — controlled OpenAI verification

## Selected CLI path

Use the [operator guide](p1-cli-adapter.md), [pinned setup](p1-cli-setup.md),
[campaign admission](p1-campaign.md) and [separate probe runbook](p1-local-probe.md).
The selected contract is CLI 1.15.0, `gpt-4o-transcribe-diarize`, `diarized_json`.
The HTTP/Whisper contract below is historical; `controlled_openai live` returns
`retired_transport_use_cli_operator` before credential access. Do not execute its old
live procedure or apply its pricing to the CLI model.

## Historical standalone HTTP harness — retained implementation record

The remaining sections document the earlier HTTP/Whisper attempt. Its source and
ledger are preserved for reuse of controls; its contract/pricing do not govern
the selected CLI model. These are historical instructions, not the next action.

P1 is a standalone local engineering harness, `scripts/p1/controlled_openai.py`.
It is not wired into API, worker, manual upload, demo settings, database provenance,
or application startup. The retired SDK/CLI commands remain retired. The owner
accepted the demo as “passable”; Section 5 is closed and OD-002 resolved.
The 2026-09-13 authorization permits local implementation and generated-only provider
verification, at most six transcription requests including retries and $2 total.
It does not authorize staging, production, real/client/human recordings, Broadvoice,
deployment, commits, pushes, publishing or external messages.

## Contract decision — official sources checked 2026-09-13

P1 selects `whisper-1`, a documented multilingual transcription model with a published
price of $0.006 per minute. The fixed request is HTTPS POST to
`api.openai.com/v1/audio/transcriptions`, multipart WAV input, `model=whisper-1`,
`response_format=verbose_json`, original language `en` or `es`, `temperature=0`,
and `timestamp_granularities[]=segment`. This is a bounded baseline verification,
not a claim that Whisper is the recommended model for ordinary transcription.
The current guide recommends `gpt-transcribe` for that role. Whisper's duration
pricing lets this test conservatively reserve whole minutes without uncertain token
estimates. There is no model fallback. Speaker diarization/identity is unavailable;
P1 does not construct product findings or import transcripts.

The API permits files up to 25 MB. P1's own limits below are stricter. The guide's
`chunking_strategy=auto` requirement beyond 30 seconds applies to
`gpt-4o-transcribe-diarize`, not Whisper. This harness deliberately sends no diarization,
known-speaker, translation, streaming, file-storage or unsupported `store` fields.
Responses must contain matching language, bounded duration, valid segment timestamps,
and the two authored garden/bicycle keywords. These are limited contract/content
checks, not a transcription-accuracy benchmark or speaker qualification.

Sources: [file transcription](https://developers.openai.com/api/docs/guides/speech-to-text),
[request/response reference](https://developers.openai.com/api/reference/resources/audio/subresources/transcriptions/methods/create),
[Whisper pricing](https://developers.openai.com/api/docs/models/whisper-1),
[data controls](https://developers.openai.com/api/docs/guides/your-data),
[project and key practices](https://developers.openai.com/api/docs/guides/production-best-practices).

The data-control table lists transcription content as not used for training, with
no abuse-monitoring or application-state retention, and ZDR eligibility. These are
published endpoint defaults, not verified firm account settings. Project data-sharing,
residency, retention overrides, terms and ownership need current owner/account evidence.
The harness currently supports only an explicitly approved global endpoint. Projects
requiring a regional endpoint must stop for a separately reviewed change.

## Enforced limits

| Control | Bound |
|---|---|
| Fixed generated cases | English, Spanish, English longer than 30 seconds |
| Audio | PCM16 WAV, mono, 16 kHz, 0–90 seconds; long case strictly above 30 |
| Audio bytes | 4 MiB per request; 24 MiB across campaign |
| Multipart body | Audio cap plus at most 4 KiB overhead |
| Requests | Six across invocations of the fixed campaign, debited before transport |
| Retries | Zero, including HTTP 429/5xx, timeout and malformed response |
| Cumulative transmitted duration | 540 seconds |
| Spending | $2 hard local reservation ceiling; each request rounds UP to a whole minute at $0.006/minute |
| Maximum reachable reservation | Six × two minutes × $0.006 = $0.072 |
| Transport | Fixed HTTPS host/path, verified TLS, no redirect/proxy/SDK fallback |
| Socket timeout / response bytes | 45 seconds per blocking operation; 256 KiB response |
| Local generator | 120-second subprocess timeout; fixed local tools and authored text |

A private, exclusively locked ledger at
`~/.local/state/colacci-law/colacci-law-p1-20260913.jsonl` survives attempt-directory
changes. Reservations are flushed and synced before client construction. A crash,
provider failure or bad response leaves an unresolved debit and blocks subsequent
live runs. There is no reset/refund switch. Preserve the ledger after cleanup; never
remove or edit it to obtain more attempts. A source/ledger modification can bypass
local controls, so this is an owner-controlled engineering guard, not an account-wide
billing quota. It cannot cap unrelated callers' spending. Published-price reservations
are not invoices; actual billed cost remains unknown without account billing evidence.

## Zero-request preflight and missing account prerequisites

From the repository root, host Python uses only the standard library:

```bash
python3 -m scripts.p1.controlled_openai preflight --evidence /tmp/colacci-p1-new-preflight
python3 -m scripts.p1.controlled_openai generate-check --evidence /tmp/colacci-p1-new-generation
```

Every evidence directory must be fresh; files are exclusive-create and private.
`preflight` without an approval lists the missing fields and exits 2 with zero
requests and zero client constructions. `generate-check` independently verifies
all three generated audio cases and removes its temporary media in `finally`.
It does not accept credentials or make provider requests.

For a live run, a firm owner must supply a private 0600 local JSON approval matching
`docs/runbooks/p1-approval.example.json`, fill in the actual organization/project IDs,
references to verified ownership/current terms/project data controls, and all explicit
confirmations. Bind it to the current harness SHA-256 and an expiry within 24 hours;
review current pricing again when preparing a later run. Do not treat example fields,
a key prefix, generic documentation, or this user's spending authorization as proof
of firm account ownership or acceptance of current account terms.

Deliver a project-scoped restricted credential through an inherited pipe descriptor
(number at least 3) from an owner-controlled secure runtime. Pass only that descriptor
number as `--key-fd`, and the approval path as `--approval`. The `live` mode re-runs
preflight before credential consumption and before each request. The credential pipe
is closed after a bounded read; no key is accepted from argv, files, environment,
source, Compose, chat, or logs. The harness does not search a personal keychain or use
ambient OpenAI credentials. It checks format; actual key permissions and project
ownership require the supplied account evidence and eventual provider response.
Preflight validates availability metadata without reading the pipe or constructing
a client. No secret or approval has been supplied in the current P1 attempt.

Successful generated media are held only in memory while submitting. Raw provider
responses are validated in memory and discarded; evidence keeps counts, duration,
boolean checks and conservative reservations, never text/headers/raw errors. Memory
is released at process exit; Python does not promise cryptographic memory erasure.
Temporary generated media are removed on normal success/failure, and cleanup failure
returns an error. Abrupt process termination may leave its private generated directory;
inspect only that attempt's directory, retain cleanup evidence, then remove it. The
campaign ledger must remain. The owner must revoke the ephemeral key at its source;
closing a descriptor is not proof of remote credential revocation.

## Verification scope

`tests/unit/test_p1_controlled_openai.py` runs offline in the pinned Python container.
It covers preflight gates, payload, language/timestamps, six-request persistence,
spend/duration/byte guards, zero retries, ambiguous failures, concurrency, corruption,
private evidence, descriptor handling, and all three mocked contract cases.
Run repository lint, strict types and unit checks plus this focused suite. Host
`generate-check` verifies actual local voice generation separately. Mock success never
qualifies live provider access. After missing prerequisites are supplied, run a fresh
zero-request preflight and the three fixed live cases using the same campaign ledger;
stop at the first failed case. All later phases remain separately authorized.
