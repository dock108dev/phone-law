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

## Recorded handoff — 2026-09-15

**Recorded September 15 status: preparation complete; USER ENTRY NEXT; paused that day.**
This is retained preparation evidence, not a fresh verification of private state.
Use the Desktop tracker for current scope and the readiness procedure below at resume. The accepted demo stays
accepted. P1D, P1E and the full P1F campaign remain paused.

The owner already replied **“approved, no additional requests.”** This resolves the
single estimated-cost attempt, the stated billing/redirect limitations, and additional
Colacci usage confirmation. Do not request these decisions again merely to resume.
The original campaign was initialized with zero historical debit after that decision;
provider usage and verified billed cost remain unknown. No fresh approval is invented.

Only the actual personal/development Platform project ID and matching project key
remain for private runtime entry. Account billing, transcription permission and model
access are unobserved until the supervised attempt. Do not collect credentials in chat,
inspect saved credentials, or claim account access from Codex sign-in.

Durable preparation, sample and private evidence live at:
`/Users/michaelfuscoletti/.local/state/colacci-law/single-probe`.
The original ledger remains in its existing parent directory, with its original
campaign ID, initialization marker, head witness and journal. Never initialize it again.

See the [current preparation report](/Users/michaelfuscoletti/.local/state/colacci-law/single-probe/REPORT-20260915.md).
The private `prepared.json` freezes the implementation fingerprint, runtime, sample,
CLI contract, runtime fixture, approval and historical evidence. `history/` preserves
previous readiness records byte for byte. The accepted demo was not changed or run.

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
The existing $2 campaign limit remains; the owner accepted the stated limitation
for this single estimated-cost attempt on September 13. No reset of historical spending is permitted.

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

## Durable resume — next session only

There is no open Terminal dependency. The old temporary `owner_run.py` launcher is
retired: its source fingerprint mismatches current source. No execution-approval or
project-selection record existed at reconciliation. No expiry was extended or backdated.
The substantive approval is retained separately from a time-limited execution binding.

1. The next supervised session verifies the frozen preparation **without prompting**:

```sh
cd /Users/michaelfuscoletti/Desktop/colacci-law
/Users/michaelfuscoletti/.local/lib/colacci-law/probe-venv/bin/python -m scripts.p1.probe_resume check
```

The stable Python environment is installed against the current hash-pinned
`requirements.txt`; it is not the old `/tmp` virtual environment. The check verifies
source/media/fixture, Python and installed versions, CLI binary, retained decision,
original campaign integrity and absence of a hold/one-use marker. It also restores
only missing historical evidence from verified durable copies to the exact paths
embedded in the original ledger. Changed evidence stops the check; the ledger itself
is never restored, overwritten, relocated or reset. If any identity check fails,
stop for bounded reconciliation; do not refresh `prepared.json` automatically.

2. After that check passes, open a **new owner-local Terminal** and run:

```sh
cd /Users/michaelfuscoletti/Desktop/colacci-law
/Users/michaelfuscoletti/.local/lib/colacci-law/probe-venv/bin/python -m scripts.p1.probe_resume enter
```

This is the only supported private-entry launcher. It verifies preparation before
asking for the actual personal/development Platform project ID. Local entry binds
that project to the frozen source/sample and retained original decision in a new,
uniquely named execution record with current `issued_at` and a one-hour expiry.
It never edits an older execution record or treats the substantive decision as an
indefinite execution window. Expired, future-dated, mismatched or over-24-hour windows
are rejected. Key/project matching is the owner's local selection, not a claim of
provider-verified account access.

3. Existing admission revalidates the record under the original campaign lock,
reserves one attempt and writes the one-use marker **before** the hidden key prompt.
Key entry fails closed if echo suppression is unavailable. Source and expiry are
rechecked after private key entry and before dispatch, so waiting at the prompt cannot
outlive the execution window. The key passes through a
bounded pipe into the restricted CLI child environment, with no saved key or argv value.
Cancellation after reservation retains the debit/hold; it does not authorize another try.
No automatic retry runs. Never invoke `prepare` to replace missing approved media.

4. Stop after this one attempt. Fixed diagnostics and sanitized result/usage evidence
are retained privately; CLI children, relay, temporary media and the prepared WAV are
removed in attempted-run cleanup. The sample receipt and historical evidence remain.
A valid transcript still retains the accounting hold for unverified physical request
count/billing. Review those facts before any separately authorized later work. No P1D,
P1E, full P1F, production or client readiness is implied. Python string zeroization is
not guaranteed; key references are released and no key is saved.

**USER ENTRY NEXT — Owner enters the actual personal/development Platform project ID
and its matching key privately through the supported local prompt. The next session
verifies the prepared identity and fresh execution binding, then performs the single
supervised probe and stops.**

The September 15 pause did not authorize an unattended later launch. No live probe ran on September 15;
no credentials were accessed and no new reservation, dispatch or spending occurred.

## Local Git handoff

The September 15 handoff described five uncommitted files. Those changes were
subsequently committed in `db42ce3fdc06a667434b9e5341cc3db27dd01534`; do not repeat
the old five-file staging instructions. Review current Git status before any owner-managed
Git action. The Desktop tracker and private runtime/evidence remain outside the repository.

Prepared content identity and Git identity are distinct. A commit alone does not
change content hashes; changes to fingerprinted implementation or explicitly bound
files require bounded reconciliation. Never refresh preparation just to make a
check pass. Documentation reconciliation does not claim a fresh probe readiness
check, credential check, live result or candidate qualification.

## Focused offline checks

```sh
python -m pytest tests/unit/test_p1_local_probe.py tests/unit/test_p1_campaign.py tests/unit/test_p1_cli_adapter.py tests/unit/test_p1_cli_check.py
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
