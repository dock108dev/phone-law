# One supervised local development probe

Scope correction, 2026-09-13: P1D is paused. This probe uses one invented,
locally synthesized English sample. P1A–P1C evidence is preserved; their earlier
firm-account/P1D/P1E/full-P1F admission requirements are superseded for this probe
only. Firm/client/production controls and application provider blocks remain.
No full English/Spanish/long-audio campaign, product rehearsal or release is authorized.

## Exact prepared sample and identity

Text: “This is an invented local development test. The blue bicycle is beside the
garden. Tomorrow we will count yellow flowers and write a short note.”

Built-in macOS `say`, Albert, rate 140, then `afconvert`, mono PCM16 16 kHz.
Generation ran with networking denied; no human recording or cloned voice.
Duration **10.6993125 seconds**; **342,422 bytes**; SHA-256
`2dac48bd52338aacb4b42b8cd01785deb9666eaf6e424f5ac5a6d200fc50dffa`.
Private receipt includes generator executable hashes. Media is retained only pending
this decision/attempt and deleted in the attempted-run cleanup. Do not regenerate
and silently reuse approval: approval binds the exact media hash and source.

CLI **1.15.0**:
`/Users/michaelfuscoletti/.local/lib/colacci-law/openai-cli/1.15.0/bin/openai`;
SHA-256 `db54c56a0df645a261095808cd83c5a6690b89589145859719229d32ac4c46db`.
Command remains `audio:transcriptions create`, model `gpt-4o-transcribe-diarize`,
`diarized_json`, scalar auto chunking, JSON output, scalar English stdin body.
Existing adapter supplies arguments, bounded process execution and strict conversion.
No SDK/direct-HTTP transcriber replaces the CLI. The relay carries opaque TLS bytes.

## What is needed now

1. Owner identifies a personal/development **or** firm Platform project, with its
   project ID. Firm ownership is optional for this generated development probe.
   Its project key must allow transcription and the project needs billing/model access;
   those capabilities are not proven before this first request. Codex sign-in does
   not itself provide this transcription API credential or API billing entitlement.
2. Confirm whether any **additional Colacci campaign provider requests** occurred.
   Reuse P1C's reviewed zero-request records. No unrelated account-wide history is
   required. Carry forward any additional usage or ambiguity, never invent zero.
3. Explicitly authorize this single estimated-cost attempt despite the inability to
   guarantee the existing absolute $2 billing ceiling. Also decide whether to accept
   the residual same-origin redirect GETs and unverified physical request count.
   This is not blanket approval or a silent redefinition of the six-request/$2 cap.
   Without that explicit decision, execution remains blocked.

The actual owner decision is retained as a private hash-bound non-secret record.
No passing approval or reconciliation has been authored in advance.
No account or saved personal credential has been inspected.

## Pricing: estimate, not a maximum

Current official [exact-model page](https://developers.openai.com/api/docs/models/gpt-4o-transcribe-diarize)
shows $2.50 input and $10 output per million tokens, a 16,000-token context and
2,000-token output limit. The current [general pricing page](https://developers.openai.com/api/docs/pricing)
does not expose an exact diarize row in the fetched view. Do not substitute another
model's per-minute price.

For this short sample, use a deliberately oversized planning assumption of one
full 16,000 input-token window and 2,000 output tokens:
`16,000 × $2.50 / 1,000,000 + 2,000 × $10 / 1,000,000 = $0.06`.
These assumed token quantities are not measured usage or proof of total internal
processing. **$0.06 is a conservative planning estimate, not a guaranteed maximum.**
No local reservation, project alert or model context limit guarantees a billing cap.
The existing $2 spending limit remains unchanged until the owner explicitly decides
about this one exception. No reset of historical spending is permitted.

Record separately: local reservation ($0.06 if admitted), estimated cost ($0.06),
provider numeric usage (if returned), estimated charge derived from known billable
units (only if sufficient), and verified billed charge (unknown absent billing evidence).

## Transport and accounting limits

Fixed initial endpoint: `https://api.openai.com/v1/audio/transcriptions`.
A temporary loopback CONNECT relay permits only `api.openai.com:443`, once. CLI
Seatbelt permits only that loopback port. Proxy settings are explicit child-only
values; ambient proxies, config homes, CA overrides and debug settings are excluded.
The CLI verifies the provider certificate normally. No TLS interception, custom
trusted certificate, SDK replacement or credential in a command argument is used.
The relay rejects plaintext HTTP, other destinations and a second tunnel.

P1C observed 301/302/303 follow-up GETs with authorization to another same-origin
path; tested 307/308 did not replay the upload. Such GETs can still use the original
TLS connection. The relay cannot see encrypted HTTP paths or count those requests.
**One CLI transcription invocation, no automatic retries, is not proof of one
physical HTTP request or an absolute six-HTTP-request ceiling.** No unsupported
no-redirect flag was found in the pinned CLI. Owner acceptance of this precise
residual limitation is required before the probe. If unacceptable, stop here; a
pinned CLI change exposing redirect refusal would need separate engineering scope.

Admission locks the original shared campaign state, checks the exact source, input,
project, approval expiry and remaining capacity, reserves one attempted transcription,
10.699313 seconds (rounded up), 342,422 bytes and 60,000 micro-US dollars, then writes
a one-use marker before acquiring credentials and dispatching. Historical debits,
corrupt/missing-state rejection and ambiguous holds are preserved. There is no reset,
refund, alternate campaign ID or generic safety bypass. A successful transcript still
leaves a campaign hold because physical GET count and billed cost are unverified.
Do not automatically resume P1D or send another request.

## Exact procedure after the owner's decisions

Use the retained host environment (Python 3.14.5; focused checks also run with pinned
Docker Python 3.14.7). From the repository root:

```sh
/tmp/colacci-law-p1b-20260913/venv/bin/python -m scripts.p1.local_probe prepare
```

This rechecks the already prepared sample; it does not overwrite or upload it.
After the owner confirms Colacci history, retain that response and combine it with
`/tmp/colacci-law-p1c-20260913/evidence/reconciliation-final.json` and its referenced
records. Follow the existing campaign runbook's explicit initialization schema.
Only if history is resolved and no state exists, create the private stable state
directory and use `scripts.p1.operator --initialize` with the real reconciliation.
Existing state must be reused; no initialization merely because a file is absent.

Write a private canonical approval JSON with `campaign.encoded` using the validated
fields in `local_probe.approval_record`: actual owner decisions, selected project ID,
account kind, reviewer, expiry within 24 hours, current implementation/CLI contract/
media hashes, one request/no retries, $0.06 estimate, and explicit spending/redirect/
physical-count decisions. Bind the actual owner-decision record by path/SHA-256.
An example or generated checklist is not the owner's approval.

```sh
/tmp/colacci-law-p1b-20260913/venv/bin/python -m scripts.p1.local_probe preflight --approval /absolute/private/approval.json
/tmp/colacci-law-p1b-20260913/venv/bin/python -m scripts.p1.local_probe run --approval /absolute/private/approval.json
```

The second command must run in the owner's local interactive terminal. **Only after
reservation**, it prompts without echo for the selected project's key. Never paste a
key into chat. It uses the existing bounded pipe reader and child-environment delivery;
no key file, shell history value, source/Compose entry or saved credential lookup.
If a key is not available, cancel; any reservation remains held. The owner can revoke
an ephemeral project key afterward; no revocation is claimed without account evidence.

On timeout, process error or malformed response: retain debit, save a fixed diagnostic,
remove media and stop. No retry. On valid output: retain only sanitized invented text,
timestamp/speaker counts, numeric provider usage and source/project/input identity;
never publish the converter's mocked provenance as a live application artifact.
One success proves only this observed local path, not general accuracy, multi-speaker
quality, client acceptance or production readiness. `getpass`/pipe references are
released and the child, relay and temporary media are cleaned up; in-memory zeroization
cannot be guaranteed by Python strings. The private sample receipt remains.

## Focused offline checks

```sh
python -m pytest tests/unit/test_p1_local_probe.py tests/unit/test_p1_campaign.py tests/unit/test_p1_cli_adapter.py
python -m scripts.p1.offline_tunnel_check
python -m scripts.p1.offline_probe_check
python -m scripts.p1.offline_serialization_check
```

TLS harness uses a local socket-pair upstream replacing the only outbound connect
function, dummy credentials and an untrusted certificate; the real CLI child is
Seatbelt restricted to the relay. It proves certificate rejection before application
bytes, not positive provider TLS. Relay checks independently prove fixed destination,
one tunnel and opaque forwarding. P1B/P1C positive serialization/retry/redirect evidence
is reused. No system trust changes or real provider connection occur in these checks.
Normal startup/tests remain offline. Full P1D/P1E/P1F are deferred.
