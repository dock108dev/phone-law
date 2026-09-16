# P1A: pinned host OpenAI CLI

P1A installation evidence below is retained. See the [operator guide](p1-cli-adapter.md)
for the implemented adapter, campaign admission and separate supervised probe.
API, worker and browser remain offline. No account credential is needed for
installation or offline capability checks. The Desktop tracker owns current status.

## Installation identity and reproduction

Reviewed 2026-09-13: official resource CLI **1.15.0**, macOS ARM64.
Selected executable on this Mac:
`/Users/michaelfuscoletti/.local/lib/colacci-law/openai-cli/1.15.0/bin/openai`.
The machine-independent default is the same suffix under the operator's home.
The checker never searches PATH. `--executable /absolute/path` permits an alternate
location only for the identical approved binary, not a version or digest override.

Installed using the [official Homebrew method](https://developers.openai.com/api/docs/libraries/openai-cli#installation):
`HOMEBREW_NO_AUTO_UPDATE=1 brew install --cask --no-binaries --require-sha openai/tools/openai`.
Homebrew verified the official archive checksum. `--no-binaries` avoided the existing
Python executable collision. Its binary at `/opt/homebrew/Caskroom/openai/1.15.0/openai`
was copied to the dedicated versioned path above, so a later Homebrew upgrade does
not silently replace Colacci's selection. No shell profile, global executable or
Python environment was replaced. The legacy `/opt/homebrew/bin/openai` remains the
Python SDK 1.3.7 entry point owned by `/opt/homebrew/lib/python3.13/site-packages`.

The Homebrew command alone follows the current cask and is **not** a reproducible
version pin. The reviewed cask is
[`9df0601f09dcafd260bf1e667486e9839bc486b9`](https://github.com/openai/homebrew-tools/blob/9df0601f09dcafd260bf1e667486e9839bc486b9/Casks/openai.rb).
For exact reproduction, extract the **same official release artifact** below,
with both its cask/archive checksum and installed-binary checksum fixed by
`scripts/p1/cli-contract.json`. This avoids relying on a later cask or `latest`.
Run from this repository on an ARM64 Mac:

```bash
python3 - <<'PY'
import hashlib, io, json, platform, zipfile
from pathlib import Path
from urllib.request import urlopen

assert platform.system() == 'Darwin' and platform.machine() == 'arm64'
lock = json.loads(Path('scripts/p1/cli-contract.json').read_text())
with urlopen(lock['archive_url'], timeout=60) as response:
    archive = response.read(64 * 1024 * 1024 + 1)
assert len(archive) <= 64 * 1024 * 1024
assert hashlib.sha256(archive).hexdigest() == lock['archive_sha256']
with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
    binary = bundle.read('openai')
assert hashlib.sha256(binary).hexdigest() == lock['binary_sha256']
target = Path.home() / lock['relative_install_path']
target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
if target.exists():
    assert hashlib.sha256(target.read_bytes()).hexdigest() == lock['binary_sha256']
else:
    with target.open('xb') as output:
        output.write(binary)
    target.chmod(0o755)
print('Pinned official release installed or already identical')
PY
make p1-cli-check
```

Archive: [OpenAI 1.15.0 macOS ARM64 release](https://github.com/openai/openai-cli/releases/download/v1.15.0/openai_1.15.0_macos_arm64.zip).
Archive SHA-256: `406b6c59ba43849850fa8ab02ef8191dac718b58d6044c5759741ff166fa8001`.
Binary SHA-256: `db54c56a0df645a261095808cd83c5a6690b89589145859719229d32ac4c46db`.
Release checksums and GitHub asset digest agree with the cask. These establish
artifact integrity from the official distribution, not an independent signature
attestation. Other platforms/builds require a reviewed lock update; matching a
version string alone is insufficient. Lead agents are authorized by the owner to
install/update needed tools, while preserving unrelated installations.

## Frozen contract and evidence basis

| Concern | Selected contract | Evidence |
|---|---|---|
| Command | `audio:transcriptions create` | Installed root/transcription help and official CLI guide |
| Model | `--model gpt-4o-transcribe-diarize` | Installed help; official transcription reference |
| Provider response | `--response-format diarized_json` | Installed help; speaker segments documented by OpenAI |
| Original language | Transcription endpoint preserves input language; omit hint for automatic detection | Installed help and speech-to-text guide |
| Explicit hint | Optional ISO-639-1 scalar `language` in authored JSON/YAML stdin, e.g. `{"language":"es"}`; do not use ambiguous `--language` in this release | Inspected flag/body merge source; actual loopback serialization verified in P1B |
| Chunking | `--chunking-strategy auto` (two argv elements), required beyond 30 s; safe to request for all selected inputs | Installed help, generic YAML scalar parser, upstream transcription test, official guide |
| Machine output | Global `--format json`; no transform, raw output or streaming | Installed root help and output handler source |
| Credential | Ephemeral child-only `OPENAI_API_KEY`; never a secret argv flag | Official CLI guide and source; auth flags are absent from rendered help |
| Endpoint | Explicit `--base-url https://api.openai.com/v1`; SDK default is production; flag overrides `OPENAI_BASE_URL` | Root help, CLI `cmdutil.go`, SDK client/options |
| Configuration | CLI flags/environment and optional stdin request body; no automatic dotenv/config-file loader found in inspected startup/client path | Inspected source; private HOME/cwd and allowlisted environment still required |
| Retries | Multipart containing a file upload sets `WithMaxRetries(0)` automatically; no global retry flag in this release | Inspected `multipartbody.go` and upload path; **not help-derived** |

There are two `--language` definitions in 1.15.0: scalar `language` and array
`languages` (the latter belongs to another model). Do not infer correct scalar
serialization from help. Body-map input avoids that name collision; P1B verified its authored scalar with the actual pinned CLI under external-network denial.
Omitting the hint is also valid original-language transcription. Do not send
`languages`, prompts, logprobs, timestamp granularity or known-speaker recordings.
Defaults shown in help do not imply those optional fields are sent: request
extraction includes only explicitly set flags. Chunking's `auto` is a scalar,
not `{type:auto}` or a quoted JSON object.

Source inspection is bound to [CLI v1.15.0](https://github.com/openai/openai-cli/tree/v1.15.0):
`pkg/cmd/audiotranscription.go`, `audiotranscription_test.go`, `flagoptions.go`,
`multipartbody.go`, `cmd.go`, `cmdutil.go`, `mtls.go`,
`internal/requestflag/requestflag.go` and `cmd/openai/main.go`.
Its `go.mod` pins `openai-go/v3` **3.60.0**. That SDK normally defaults to two
retries (including certain errors/408/409/429/5xx); file uploads override this to
zero in this CLI. Scalar-only requests do not inherit that guarantee. This is
CLI implementation inspection, not a proposal to call an SDK directly.

P1B must rebuild the child environment, excluding ambient base URL, admin keys,
custom headers, proxies, organization/project values, mTLS file settings, debug
and pager settings. Later approved project context must be explicitly admitted.
No generic credential file or pipe-FD flag is established by this CLI; P1B can
consume an approved ephemeral input and supply the CLI's verified environment
mechanism. P1C must preserve durable debits and account for redirects/ambiguous
execution; zero SDK retries alone is not proof of every physical request.

Official sources: [CLI guide](https://developers.openai.com/api/docs/libraries/openai-cli),
[transcription CLI reference](https://developers.openai.com/api/reference/cli/resources/audio/subresources/transcriptions/methods/create),
[speech-to-text/diarization](https://developers.openai.com/api/docs/guides/speech-to-text#speaker-diarization).
No help/source inspection proves account access, billing, live response shape,
transcription quality, or provider behavior.

## Zero-request verification

`make p1-cli-check` uses host standard-library Python. It checks the binary digest
before execution, then version, root help and transcription help against exact
reviewed hashes and required capabilities. Missing, legacy, unapproved, changed
version and capability failures produce fixed setup codes and exit 2. It never
reads account configuration, credentials or audio, and never runs an API action.
Each help subprocess has a 10-second deadline and combined 64-KiB output cap,
private empty HOME/cwd, DEVNULL stdin, closed inherited descriptors and process
group cleanup. Raw child diagnostics are never printed. This is an offline
capability guard for trusted local installation, not a sandbox against an owner
concurrently replacing executable bytes.

Focused tests: `pytest tests/unit/test_p1_cli_check.py`. Negative identities and
help contracts are deterministic doubles. Bounded help-runner tests use tiny
local shell doubles, including timeout/output failures and ambient-secret
exclusion. They exercise this inspection runner, not the pending adapter runner.
Run them under Docker `--network none`; macOS coverage is recorded separately.
Ordinary repository lint/types/unit tests remain required. P1E's broader
application/CI matrix is separate; prior accepted-demo results do not qualify
changed source.
