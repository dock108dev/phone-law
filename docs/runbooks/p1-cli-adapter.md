# P1B offline CLI adapter

P1B implements an explicit host operator boundary, bounded POSIX process primitive,
and strict conversion into the existing `Transcript` contract. It does not connect
an application to OpenAI. P1C durable admission/preflight and P1F live verification
remain pending. The original six-request/$2 campaign is unchanged and unused here.

## Selection and execution

`python -m scripts.p1.operator --profile local_dev --transport openai_cli_local --offline`
runs an invented in-memory response through the adapter. Omit `--offline` and it
returns `p1c_required` before tool or credential access. Other profiles/transports
are rejected. `OperatorSelection` is separate from shared `Settings`, which still
rejects CLI selection in every application profile. API, worker, browser, demo and
ordinary tests have no CLI dependency. No environment flag enables live execution.

The injectable `Runner` protocol supports process-free unit tests. The default
`LiveRunner` always fails closed. The private process primitive also rejects every
non-loopback endpoint, so calling it directly cannot reach a provider in P1B.
The pinned Mac process is always wrapped in loopback-only Seatbelt by the primitive.
Endpoint substitution and executable substitution exist only for explicit offline
harnesses; there is no operator flag for either. P1C must deliberately replace this
lock with durable reservation/preflight before wiring production execution.

## Serialization established with the actual pinned CLI

Reuse [P1A tool identity](p1-cli-setup.md). The actual 1.15.0 binary, verified by
SHA-256 and all capability hashes, submitted generated silent WAV bytes to a
controlled loopback capture server under macOS Seatbelt external-network denial.
The exact multipart fields were `file`, scalar `language=es`,
`model=gpt-4o-transcribe-diarize`, `response_format=diarized_json`, and scalar
`chunking_strategy=auto`. The language comes from authored JSON stdin, never the
ambiguous `--language` flag. Automatic chunking is requested for every input,
including the 31-second capture input. `--format json` returned a JSON object.
The command uses transcription, never translation.

Each of success, HTTP 408/409/429/500, and dropped connection produced exactly one
physical loopback upload. This runtime evidence supplements P1A's source inspection
of zero upload retries; no adapter retries exist. Redirect behavior, other failures,
actual account access, billing, response quality and provider behavior remain
unproven. P1C must account for physical requests and ambiguous execution.

## Process guarantees and evidence distinctions

The primitive verifies the absolute executable against P1A before running it, uses
direct argv with no shell, and reconstructs the child environment from only HOME,
TMPDIR, PATH, LC_ALL and explicit child-only OPENAI_API_KEY. No ambient credentials,
keychain, configuration, proxy, endpoint, pager, debug, organization or project
settings are consumed. Inputs are private bytes written as generated.wav in a
0700 temporary directory with 0600 file permissions and private HOME/cwd.

Nonblocking stdin/stdout/stderr share a selector, a combined 256-KiB output cap,
and a maximum 120-second child deadline. Cancellation is polled at most every
25 ms. Finally, the whole process group is killed, the direct child is reaped,
pipes are closed and the input directory removed. Cleanup failure overrides other
failures. Diagnostics are fixed typed codes and never include output, transcript
content, credentials or media paths. Request and mock payload reprs are disabled.
The executable check assumes the owner does not concurrently replace approved
binary bytes, as in P1A; it is not a hostile local-user sandbox.

Fake-runner unit tests spawn no process. Separate OS-isolated fake-executable
checks cover successful output, malformed bytes, early exit, concurrent overflow
of both streams, timeout, cancellation, descendants retaining pipes, spawn failure
and input removal. Broken stdin and cleanup failure use deterministic OS fault
injection and are labeled as such. macOS checks allow the OS-added
`__CF_USER_TEXT_ENCODING`; it is not inherited from the operator environment.
Linux may briefly expose a dead descendant as a zombie until container init reaps
it; tests require termination, and `--init` handles orphan reaping. These are
separate from real-CLI multipart evidence and do not establish provider behavior.

## Conversion

The converter retains original-language text and valid segment timestamps, including
overlap and non-monotonic segment ordering allowed by the existing contract.
Every timestamp must be finite, numeric (not bool/string), start before end, and
within the supplied input duration. Empty/missing speakers, wrong types, malformed,
truncated or duplicate-key JSON, invalid segments and text/segment disagreement
are rejected. English/Spanish is the existing contract limit; the explicit source
language comes from the generated-input request, not invented detection. A supplied
provider language must agree. No translation, confidence or identity is fabricated.

Speaker labels are mapped in first-seen order to speaker-001 etc. All roles remain
unknown participants with unknown identity. Safe transport provenance adds the
additive `mocked_cli` result kind to the existing schema, distinct from fixture,
transcript-only and separately authorized live data. Mocked output never claims an
observed CLI version. Generated schemas are refreshed; no database migration or
second transcript schema is added. The existing import validator is unchanged:
CLI provenance cannot masquerade as its specifically invented import fixture.
P1D's actual import/product rehearsal remains pending.

## Repeatable offline checks

Use the repository's pinned Python dependency image and source-matching disposable
copy, as described in [CI reproduction](../continuous-integration.md). Host checks
need an isolated Python environment containing the pinned requirements; the Mac
Python 3.14.5 run is supplemental to required Docker Python 3.14.7 checks.

```sh
# Ordinary unit tests: no child processes in the P1B adapter tests.
pytest tests/unit/test_p1_cli_adapter.py
# Explicit invented operator check:
python -m scripts.p1.operator --profile local_dev --transport openai_cli_local --offline
# Mac fake-process behavior; replace python with the isolated environment's absolute interpreter.
sandbox-exec -p '(version 1)(allow default)(deny network*)' python -m scripts.p1.offline_process_check --network-denied
# Linux fake-process behavior, using the freshly built disposable API image:
docker run --rm --init --network none IMAGE python -m scripts.p1.offline_process_check --network-denied
# Actual pinned Mac CLI; only its controlled loopback listener is permitted.
python -m scripts.p1.offline_serialization_check
```

Run lint, types, unit tests and generated-schema checks on final source. This slice
also runs integration and smoke for the shared provenance schema. No UI code changed;
browser qualification and P1D/P1E workflow work are not claimed. Keep all evidence
private and clean up only attempt-owned resources. Never reuse the owner demo.

## P1C accounting update

See [P1C campaign admission](./p1-campaign.md) for current zero-request preflight, durable reservations, reconciliation and explicit live blocks. P1B/retired HTTP instructions above are historical where superseded. P1D reproducible product rehearsal is next; live verification remains P1F.
