# Security validation — 2026-09-06

Scope: working source on base `5a59ead`, preserving the preceding uncommitted
error-handling changes. This is local implementation validation, not a clean
candidate qualification or production approval. Evidence is retained under
`/tmp/colacci-law-security-evidence/`; each record is tied to this working source
through `source-hashes.json`.

## Checks

| Check | Result | Evidence |
| --- | --- | --- |
| Ruff formatting and lint for `apps packages scripts tests` | Passed | `python.log` |
| Bandit for `apps packages scripts` | Passed; 206 existing annotation warnings unchanged from prior handoff | `python.log`, `warning-comparison.txt` |
| Dependency-pin verification, generated-schema consistency, secret scan | Passed; 25 schemas unchanged, no secret findings | `python.log` |
| `mypy apps packages scripts` | Passed; 100 source files | `python.log` |
| `pytest -m "not integration" --cov --cov-report=term-missing` | 287 passed, 18 deselected; 82.23% coverage | `python.log` |
| `pytest -m integration` | 18 passed, including roles, denied writes, upload rejection, persistence and recovery | `integration-final.log` |
| `npm run lint`, `npm run typecheck`, `npm test -- --run`, `npm run build` | Passed; 10 web tests | `web.log` |
| `make test-e2e` with isolated overrides below | Seven browser journeys and log-privacy check passed; owned runtime/stack removed | `e2e-final.log` |
| `python scripts/test_audio_boundary.py` | Passed: six accepted, five rejected, 11 confirmed deletions, zero remaining | `media-boundary.log` |
| Installed ffprobe and ffmpeg HTTP-input policy probes | Both rejected HTTP before network connection using the file-only protocol policy | `protocol-policy.log` |
| `python scripts/smoke.py` | Five components passed: API, worker, web, dashboard, database/migration | `smoke-final.log` |
| `pip-audit --require-hashes -r requirements.lock` | No known vulnerabilities | `python-audit.log` |
| `npm audit --audit-level=high` | Zero vulnerabilities | `web-audit.log` |
| `git diff --check` | Passed | Final workspace check |

The 15 new security regression cases cover invalid/deceptive Content-Length,
chunked input, exact byte limits, rejection before body consumption, safe 413
translation, validation redaction, pre-decode fingerprint rejection, both media
parser commands, and preservation of the configured logging level. Existing
error-handling and role tests remain in the complete suites.

## Runtime and isolation

Python checks used `colacci-law-api:latest` with current source mounted read-only,
`PYTHONPATH=/workspace`, and cache/coverage output in the disposable container.
The pinned runtime and dependencies were already verified in the preceding
handoff and were not changed. Browser images were built from this source.
Web checks used the prior freshly built image with current web source mounted
read-only; no frontend implementation or dependencies changed in this review.

One-off containers explicitly used the distinct label
`com.docker.compose.project=colacci-law-security-checks`. Unit and media checks
used `--network none`; database and smoke services used the separately created
internal `colacci-law-security-integration` network and `colacci_test` database.
Only advisory scans contacted external vulnerability services. Product-provider
calls, real client data, human recordings and notifications remained outside scope.

Final browser command:

```bash
COLACCI_E2E_PROJECT=colacci-law-security-final \
SLICE4_RUNTIME_ROOT=/tmp/colacci-law-security-final-runtime \
SLICE4_EVIDENCE_DIR=/tmp/colacci-law-security-final-evidence \
make test-e2e
```

The source quality commands were the Python/Web commands from
`make lint typecheck test build`, run in isolated containers rather than the
retained demo's Compose project. Integration used the standard pytest marker on
a fresh migrated test database and generated upload fixtures. Offline media was
generated on macOS into a task-owned root, then mounted at the harness's expected
`/tmp/colacci-law-slice3a` inside the container. No retained demo service was
reconfigured or restarted during this security review.

The first complete suites passed before the final logging-level regression was
added. The final Python, integration and browser suites were repeated after that
change. Earlier result logs are retained and are not substituted for final ones.

## Remaining validation boundaries

Hosted CI/CodeQL and full exact-candidate release/owner-acceptance campaigns were
not run on this uncommitted working source. Run them after the owner-managed Git
handoff. Live provider, IdP, TLS, cloud storage, ingress quotas, image supply-chain,
network and retention controls need their separate authorized deployment checks;
local tests cannot establish them. See the prioritized roadmap in the
[security review](hardening-review.md).
