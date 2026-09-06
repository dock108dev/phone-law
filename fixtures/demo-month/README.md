# Full-month synthetic transcript fixtures

`manifest.json` is the immutable recipe for the July 2026 synthetic month. The fixed seed,
daily volumes, totals, distributions, and scenario contract are versioned; application code
materializes the 500 invented entries deterministically. No audio, provider output, person,
client, case, phone number, or external identifier is present.

## Representative morning (Slice 7A)

`morning-v1.json` is the bounded `demo-morning-2026-07-v1` selection for the same
`DemoMonthManifest` / `DemoMonthCallSource` / fixture pipeline used by the month.
It contains exactly ten authored conversations for July 15, 2026, seed `20260715`,
with simulated morning July 16. It declares coverage only for July 15; other dates
are unavailable unless a separate persisted report verifies their coverage.
The historical `manifest.json` recipe is unchanged.

`morning-transcripts-v1.json` retains the original authored utterances;
`morning-expectations-v1.json` is the independently written content-review oracle.
The deterministic adapter consumes the existing `expected_facts` and
`expected_analysis` entry shape in `morning-v1.json`. Tests compare its results to
the independent oracle and original utterances; no model or external API is used.
The explicit-entry selection can be incorporated into the later replacement month.

Use only a separate disposable synthetic project, never the retained owner dataset:

```bash
export COMPOSE_PROJECT_NAME=colacci-law-slice7a
export COMPOSE_FILE=docker-compose.yml:infrastructure/local/slice7a-compose.yml
docker compose build api worker web e2e
docker compose up -d --wait db
docker compose run --rm api python scripts/seed_demo_month.py --manifest fixtures/demo-month/morning-v1.json
docker compose up -d --wait api worker web
```

The application opens at `/` with the versioned simulated morning once this set is
persisted. `/briefing/YYYY-MM-DD` selects another date explicitly. Without this
scenario, `/api/briefing` selects the previous New York calendar date, including
weekends. Missing coverage never implies zero activity. Every received call gets
one recap or an unavailable-result entry, independently of report section count.

The Slice 7A network is internal. The tested browser path is `http://web:5173`
inside that network. The desktop browser could not reach the published 15174 port
on the inspected Docker host; host-browser launch qualification remains Slice 7C.
Do not remove isolation to treat this engineering path as an owner launch.

Reproduce the morning browser journey and private screenshots:

```bash
mkdir -p /tmp/colacci-law-slice7a-browser
chmod 700 /tmp/colacci-law-slice7a-browser
SLICE4_EVIDENCE_DIR=/tmp/colacci-law-slice7a-browser docker compose --profile e2e run --rm e2e npm run test:e2e -- --project=morning-briefing
```

`make test-ui-redesign` and `make test-e2e` retain their original technical fixture
journeys, then reset only their disposable test database and run this morning
selection separately. They do not replace the retained owner's dataset or qualify
the replacement month. The tracker owns completion/readiness status.
