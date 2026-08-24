# Technology choices and pinned versions

## Gated live verification

The existing pinned OpenAI Python SDK and `httpx2` client support the bounded file
transcription probe. The SDK client is created only after profile, authorization,
credential-presence, endpoint, model, media-source, and budget validation; SDK retries
are disabled so the application owns the single global retry allowance. SQLite is used
only as a disposable live-test evidence store, so no schema migration is added.

| Layer | Exact version | Reason |
|---|---:|---|
| Python | 3.13.5 | Stable modern runtime with supported FastAPI/Pydantic/SQLAlchemy wheels; avoids adopting Python 3.14 in the foundation |
| pip | 25.2 | Exact installer in the Python image |
| FastAPI | 0.141.1 | Small typed health API with mature ASGI testing; permits patched Starlette 1.x |
| Starlette | 1.6.0 | Patched ASGI layer selected above advisories affecting the initial pre-1.0 pin |
| Pydantic Settings | 2.10.1 | Typed environment parsing and model-level fail-closed validation |
| SQLAlchemy | 2.0.43 | Explicit connection handling and portable readiness checks |
| Psycopg | 3.2.9 | PostgreSQL driver with a pinned binary wheel |
| Alembic | 1.16.5 | Reversible, inspectable database migrations |
| Uvicorn | 0.35.0 | Minimal API process with access logging disabled |
| OpenAI Python SDK | 3.2.0 | Exact candidate file-transcription SDK behind an injected, network-blocked transport; no normal live factory |
| ffmpeg / ffprobe | 7:5.1.9-0+deb12u1 | Exact Debian media inspection and normalization package; fixed arguments preserve channel count |
| Node.js | 22.18.0 | LTS-generation runtime, pinned to a patch release |
| npm | 10.9.3 | Lockfile v3 package manager, pinned in image and manifest |
| React / React DOM | 19.1.1 | Typed dashboard shell |
| TypeScript | 5.9.2 | Strict static checks |
| Vite | 7.3.6 | Local development server and deterministic production build; selected above known file-read advisories affecting earlier 7.x patches |
| Playwright | 1.55.1 | Pinned Chromium end-to-end flow and responsive screenshots in a version-pinned image |
| axe-core Playwright | 4.10.2 | Automated WCAG 2 A/AA and 2.1 A/AA checks on report and call views |
| PostgreSQL | 17.6-alpine3.22 | Supported database major with an exact patch/OS image tag |

All direct Python requirements are exact in `requirements.in`; Linux's conditional SQLAlchemy
`greenlet` dependency is explicit so the macOS-generated lock remains complete in Linux
containers. `requirements.lock` freezes the
complete transitive graph with SHA-256 hashes. JavaScript direct and transitive dependencies are
exact in `package.json` and lockfile v3. Python, Node, npm, and PostgreSQL container tags include
patch versions. Images are not digest-pinned because the supported local platforms differ; this
is a documented residual reproducibility risk.

Ruff 0.12.10, mypy 1.17.1, pytest 9.1.1, pytest-cov 6.2.1, Bandit 1.8.6,
pip-audit 2.10.0, ESLint 9.33.0, typescript-eslint 8.40.0, and Vitest 3.2.7 form the
quality toolchain.

Bandit's hardcoded all-interface rule is excluded because both Python listeners must bind across
their private container network; Compose is the enforcement point and publishes those ports on
`127.0.0.1` only. Ruff still marks each listener explicitly, and the configuration validator's
same literal is a value it rejects rather than a listener.

The 80% unit-coverage gate applies to application and shared decision logic. Thin process entry
points, migration runners, and the media/SDK boundaries are excluded from that unit-only
metric and are instead exercised by the PostgreSQL integration suite, `make test-audio`,
`make test-transcription-contract`, and live local smoke checks. The two media harnesses are
offline and produce machine-readable evidence outside the repository.
