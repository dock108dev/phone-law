# Colacci Law Call Review

P1A: the official host CLI is installed and `make p1-cli-check` verifies it with
zero provider requests and no credentials. See [pinned setup and contract](docs/runbooks/p1-cli-setup.md).
P1B adds the explicit offline `local_dev` / `openai_cli_local` operator adapter;
live execution is blocked pending P1C, and application startup remains fixture/import based. The earlier standalone
HTTP/Whisper harness is historical implementation material, not the selected P1 path.

A local application for reviewing synthetic calls: daily briefings, evidence-linked reports,
reviewer feedback, failure recovery, invented-artifact uploads and local operations.
There is no production deployment, client-data workflow or live provider integration.

## Start locally

Install Docker with Compose, `make`, a shell and host `python3` for fixture helpers. Application
Python, Node and dependencies run in pinned containers; host Node is not required.
From the repository root:

```bash
make bootstrap
make dev
make smoke
make seed-demo-month
```

Open [the local application](http://localhost:15173). `make stop` preserves the synthetic database.
For setup details, troubleshooting and a rehearsal that preserves an existing demo, see
[local development](docs/runbooks/local-development.md).

## Develop and validate

```bash
make lint typecheck test build
make test-integration
make test-e2e
```

Use [the CI reproduction procedure](docs/continuous-integration.md) to run these checks in an
isolated project. [Testing](docs/testing.md) explains focused gates and the separate online
`make audit` check. `make help` lists commands.

## Find your way

- `apps/`: FastAPI service, readiness-only worker and React web application.
- `packages/`: shared configuration, contracts, authorization, persistence and domain services.
- `fixtures/`: deterministic invented inputs; `scripts/`: development and validation entry points.
- [Documentation index](docs/README.md): setup, configuration, operations and security.
- [Architecture](docs/architecture.md) and [source ownership](docs/ssot.md): how the system fits together.
- [Maintainer guide](docs/maintenance.md): change conventions and module boundaries.

The sole roadmap and owner status live in
`/Users/michaelfuscoletti/Desktop/colacci_law_next_steps.md`; do not create a second roadmap here.
