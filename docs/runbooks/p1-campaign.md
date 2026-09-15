# P1 campaign accounting and admission

**Current scope correction, 2026-09-13:** P1D is paused. The separate
[one supervised local probe](p1-local-probe.md) is the current immediate scope.
Firm ownership, hosted staging, P1D/P1E and full P1F qualification are not
prerequisites for that probe. Its narrow admission requires actual owner project,
history, estimated-spend and residual-redirect decisions. The $2 ceiling is not
silently replaced by an estimate. Durable accounting and production/client blocks
remain. The sections below preserve the P1C implementation contract and historical
outcome; their broader live prerequisites apply to the later full campaign.

## Preserved P1C offline engineering contract

P1C implements shared durable accounting and zero-request preflight. It does not
qualify or enable live transcription. P1D is the next development slice; P1F is the
only live verification phase after P1D/P1E and all prerequisites are satisfied.
Owner demo acceptance is closed.

## Operator commands

From the repository root, with the pinned Python environment:

```sh
python -m scripts.p1.operator --profile local_dev --transport openai_cli_local --preflight
python -m scripts.p1.operator --profile local_dev --transport openai_cli_local --offline
```

Preflight accepts `--approval /absolute/private/approval.json`, `--media
/absolute/private/generated.wav`, `--provenance /absolute/private/provenance.json`
and optionally `--key-fd N`. The descriptor is inspected with fstat only, never read
or closed by preflight. The caller owns its cleanup. Preflight neither starts a
process (including help probes) nor creates state, reserves budget or makes requests.
Exit 2 means blocked; JSON separates engineering prerequisites from account evidence
and reports remaining capacity when state is readable. Missing state never means zero.
Tool checking here hashes the pinned binary and contract; the separate P1A capability
checker still verifies help output. No endpoint, executable, source, state-directory,
price or readiness override exists in the ordinary operator.

`--offline` remains the P1B invented transcript conversion check. It does not upload
or debit. Default execution enters typed admission and remains blocked. The historical
`controlled_openai live` command is retired and returns before reading credentials or
creating evidence. Its reusable generator and historical unit controls remain intact.
Neither API, worker, browser nor ordinary test startup imports a live transcriber.

## Reconciliation and explicit initialization

State is fixed at `~/.local/state/colacci-law/colacci-law-p1-20260913` with `.jsonl`,
`.initialized` and `.head` files, shared across source revisions and transport changes.
The private directory must already exist with mode 0700; do not create it as a way to
resolve missing historical state. Existing legacy `.jsonl` state blocks initialization
and requires a separately reviewed migration preserving every debit.

The P1C evidence reconciliation examined the referenced a5 report/index, hash-verified
a1/a2/a3/a4 usage/failure/cleanup records, and P1A/P1B reports. These records confirm
zero requests and zero reservations in their recorded attempts. No alternate campaign
ledger location is documented in them. No unresolved debit was found in those
records. They do not establish complete campaign/account history; unknown unrecorded
usage remains unresolved. The absent default ledger is preserved, not initialized.
The historical tracker assertion of cumulative $0 is superseded by this qualification.

Only explicit `--initialize /absolute/private/reconciliation.json` can initialize.
It validates evidence before writing anything and rejects unresolved history. Required
canonical JSON fields (use `campaign.encoded` to serialize) are:

- `schema: 1`, `campaign: colacci-law-p1-20260913`, `status: reconciled`, named `reviewer`.
- Nonempty `evidence`: absolute private file `path` and full `sha256` for every reviewed
  usage record, including an owner-verified complete-history record when needed.
- `debit`: integer `requests`, `microseconds`, `bytes`, `micro_usd`. Carry forward all
  historical reservations, including ambiguous attempts; these are not refund amounts.
- `unknown`: a list. Any nonempty list blocks initialization.

A record is a locally reviewed attestation, not cryptographic proof of account usage.
Never author a passing record from example fields or an absent ledger. P1C's retained
`reconciliation.json` is deliberately an unresolved review record, not an initialization
permit. Missing account evidence must be resolved before P1F, not by running an API
request during engineering.

## Accounting and crash rules

All monetary accounting uses integer micro-US dollars; duration uses integer
microseconds. Per input: one reserved request, at most 90 seconds and 4 MiB. Campaign:
six requests including retries, 540 seconds, 24 MiB and 2,000,000 micro-US dollars.
Each attempted retry would need its own admission; there are no automatic adapter
retries. Synthetic tests use explicit synthetic prices; they do not establish live prices.

The stable state directory is exclusively locked with POSIX flock throughout admission,
credential acquisition, dispatch and output validation. A competing process returns
`campaign_busy`. A reservation requires that lock. Genesis embeds the reconciliation
and initial historical debit. Entries form a SHA-256 chain and never remove a debit.
Each journal append is flushed and fsynced, then a separate head witness is written,
fsynced and atomically replaced, followed by directory fsync. Truncating even a complete
last entry is detected by the head witness. Files reject links, unsafe owners, public
permissions and unexpected contents; ancestry rejects unsafe writable paths.

| Transition / interruption | Durable consequence |
|---|---|
| Before initialization marker | No initialization; explicit reconciliation still required |
| Marker written, journal/head missing | Previously initialized/incomplete state; blocked, never recreated |
| Journal written before head replacement | Integrity mismatch; blocked |
| Reservation durable, before credential read | Debit retained; restart sees unresolved reservation |
| Credential/preparation fails | Debit retained; no automatic release even if no dispatch occurred |
| Dispatch marker durable, before process start | Debit retained conservatively |
| Timeout, cancellation, malformed/lost output or crash after dispatch | Unresolved debit blocks every subsequent admission |
| Validated response and durable completion | Debit retained in totals; billed cost remains separate/unknown |
| Completion append/head interrupted | Corrupt or unresolved state blocks; no inferred success |

Preflight is a snapshot. The public execution sequence rechecks under the same campaign
lock before reservation; private fault harnesses prove reserve → credential → dispatch
→ validated completion ordering. Production credential/dispatch functions intentionally
remain unavailable because pricing and redirect controls have not been qualified.
No positive live-ready result can be manufactured through approval flags.

Recovery has no reset/refund switch. Preserve the entire state directory and attempt
evidence, stop, compare the journal, head and provider/account evidence with the owner,
and prepare a reviewed additive reconciliation/migration implementation. Do not hand-edit
head files, delete markers, replay a command, or initialize another campaign to recover
budget. P1C deliberately offers no automated ambiguous-debit resolution command.
Local fsync depends on OS/filesystem/storage behavior. Accounting cannot establish
account-wide usage, coordinate another machine or stop the owner from altering/deleting
all local files. Deleting marker and journal together is not distinguishable locally
from first use; a complete-history reconciliation is therefore mandatory every time
initialization is proposed.

## Pricing and transport decision

Official model documentation fetched on 2026-09-13 local date:
[GPT-4o Transcribe Diarize](https://developers.openai.com/api/docs/models/gpt-4o-transcribe-diarize)
and [pricing](https://developers.openai.com/api/docs/pricing).
The model page lists audio token rates of $2.50 input / $10 output per million and a
2,000-token maximum output. The general pricing page did not include the exact model
name during this review. No fetched source establishes a guaranteed total billable-token
bound across automatic chunks. A context/output limit is not proof of total internal
chunk billing. A published per-minute estimate, where quoted historically, is not a
hard price ceiling. The retired Whisper $0.006/minute formula is not used for CLI pricing.

Conditional arithmetic would be ceil(input_tokens × 2.5 + output_tokens × 10) micro-US
 dollars, with any additional billable units included. The required token bounds are
unknown: the live reservation is **null**, and `pricing_upper_bound_unestablished`
blocks execution. Reserving the entire $2 without proof would still not bound charges.
A defensible model-specific bound and refreshed official evidence are prerequisites.

Pinned CLI 1.15.0 keeps P1B's observed single-upload behavior for success, 408/409/429/500
and dropped connections. The P1C real CLI harness additionally observed 301/302/303
followed by GET to a different same-origin path with dummy authorization forwarded;
307/308 did not replay the tested multipart body. Seatbelt denied destinations outside
the single allowed loopback port. Therefore the CLI cannot currently be trusted to
limit every physical request or path-level credential forwarding to an approved
production destination. `transport_redirect_boundary_unqualified` remains a hard block.
No direct HTTP/SDK replacement was added. Local captures are never provider debits.

## Approval, input and account evidence

Approval binds the implementation fingerprint (all Python/JSON under scripts/packages,
requirements lock and pyproject), CLI contract hash, exact media hash, campaign/model,
P1F generated-only scope, all campaign caps, reviewer and an integer expiry within
24 hours. Set `example: false` only for an actual reviewed approval. A mismatch or
expired record rejects it. Examples and a project key prefix do not establish ownership.

Each category in `account_evidence` references private canonical JSON by path/hash:
ownership, credential_scope, billing, terms and data_controls. Each record must be
`kind: owner_verified_account_evidence`, identify its category, project, organization,
reviewer, expiry and `example: false`; include a path/hash `support` record and the
exact category `claims` from `admission.ACCOUNT_CLAIMS`. Evidence must come from the
actual firm account/project and be owner reviewed; generic public documentation or
invented files are not acceptable support. Local schema/hash validation verifies
consistency and freshness, not the truth of an account assertion. No account was
accessed for P1C. Credential availability means a pipe exists, not that its content or
permissions have been verified; reading remains after durable admission only.

P1C preflight accepts a bounded canonical mono PCM16 16-kHz silent WAV generated
locally, plus a canonical provenance record with `generator: p1c-silence-v1`, its full
`sha256` and `language: en` or `es`. It verifies the actual silent samples and complete
WAV encoding, rather than trusting a generated-only boolean. This is an offline probe,
not a language/diarization qualification. Authored speech generation/provenance and
the reproducible product rehearsal belong to P1D; arbitrary recordings are rejected.

## Offline verification

```sh
python -m pytest tests/unit/test_p1_campaign.py tests/unit/test_p1_cli_adapter.py
sandbox-exec -p '(version 1)(allow default)(deny network*)' python -m scripts.p1.offline_campaign_check --network-denied
python -m scripts.p1.offline_redirect_check
python -m scripts.p1.offline_serialization_check
```

Mac real-CLI harnesses apply Seatbelt around each CLI child, allowing only the controlled
server port. Run fake-process and campaign harnesses inside `--network none` containers
on Linux. `--network-denied` labels the externally applied restriction; it is not itself
a sandbox. Keep real-CLI capture, fake-process behavior and injected crash results
separate. All use dummy credentials and disposable generated input/state.
