# Technology choices and pinned versions

## Offline provider contracts

The pinned OpenAI SDK supplies response/error types for injected, offline transcription tests.
The live SDK client builder and execution command have been removed. Historical configuration
and metadata remain under a documented retirement follow-up; they do not enable a provider run.

| Layer | Exact version | Reason |
|---|---:|---|
| Python | 3.14.7 | Exact application, image, formatter, type-checker, and lock-generation runtime |
| pip | 26.2.1 | Exact installer in the Python image |
| FastAPI | 0.141.1 | Small typed health API with mature ASGI testing; permits patched Starlette 1.x |
| Starlette | 1.6.0 | Patched ASGI layer selected above advisories affecting the initial pre-1.0 pin |
| Pydantic Settings | 2.15.0 | Typed environment parsing and model-level fail-closed validation |
| SQLAlchemy | 2.0.52 | Explicit connection handling and portable readiness checks |
| Psycopg | 3.3.4 | PostgreSQL driver with a Python 3.14-compatible pinned binary wheel |
| Alembic | 1.19.1 | Reversible, inspectable database migrations |
| Uvicorn | 0.52.4 | Minimal API process with access logging disabled |
| OpenAI Python SDK | 3.5.0 | Exact candidate file-transcription SDK behind an injected, network-blocked transport; no normal live factory |
| ffmpeg / ffprobe | 7:5.1.9-0+deb12u1 | Exact Debian media inspection and normalization package; fixed arguments preserve channel count |
| Node.js | 26.3.0 | Container runtime, aligned with `.nvmrc` |
| npm | 12.0.2 | Lockfile v3 package manager, pinned in image and manifest |
| React / React DOM | 19.2.8 | Typed dashboard shell |
| TypeScript | 6.0.3 | Strict static checks |
| Vite | 8.2.2 | Local development server and deterministic production build; pinned to the accepted dependency graph |
| Playwright | 1.62.1 | Pinned Chromium end-to-end flow and responsive screenshots in a version-pinned image |
| axe-core Playwright | 4.13.0 | Automated WCAG 2 A/AA and 2.1 A/AA checks on report and call views |
| PostgreSQL | 17.6-alpine3.22 | Supported database major with an exact patch/OS image tag |

All direct Python requirements are exact in `requirements.in`; Linux's conditional SQLAlchemy
`greenlet` dependency is explicit so the macOS-generated lock remains complete in Linux
containers. `requirements.lock` freezes the
complete transitive graph with SHA-256 hashes. JavaScript direct and transitive dependencies are
exact in `package.json` and lockfile v3. Python, Node, npm, and PostgreSQL container tags include
patch versions. Images are not digest-pinned because the supported local platforms differ; this
is a documented residual reproducibility risk.

Ruff 0.16.5, mypy 2.3.1, pytest 9.1.1, pytest-cov 7.1.0, Bandit 1.9.4,
pip-audit 2.10.1, ESLint 10.9.1, typescript-eslint 8.68.0, and Vitest 4.1.11 form the
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
