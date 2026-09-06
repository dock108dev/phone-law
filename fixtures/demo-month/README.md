# Full-month synthetic transcript fixtures

`manifest.json` is the preserved historical v1 recipe for the rejected July 2026 month. The fixed seed,
daily volumes, totals, distributions, and scenario contract are versioned; application code
materializes the 500 invented entries deterministically. No audio, provider output, person,
client, case, phone number, or external identifier is present.

## Replacement month (Slice 7B)

The supported default selection is `manifest-v2.json`: `demo-month-2026-07-v2`,
generator/materializer `authored-month-schedule-v2`, fixed authoring seed `20260702`.
The entries are authored, versioned inputs, not runtime-generated dialogue. The seed
fixed the materialized call timing; loading and seeding do not randomize content.
`month-entries-v2.json` supplies the existing fixture adapters. The manifest checks
SHA-256 identities for that file, original transcripts, independent expectations,
and all three unchanged morning files before ingestion. Its own byte digest is
included in seed and validation output.

The explicit 31-date schedule totals **227 expected, 226 received, 224 analyzed,
2 failed, 1 missing, 3 late, 3 duplicate deliveries**. There are 195 English and
32 Spanish inventory entries; all 32 Spanish conversations are analyzable. Weekday
volumes range from 6 to 14, averaging 10.32 over 22 active dates. Eight weekend
dates and the invented July 3 holiday closure are verified empty. These are
invented design assumptions, not measured firm statistics.

July 15 retains the ten original `CL-AM-20260715-*` identities, conversations,
facts, recaps, and segment references. `morning_identity_mapping` is an explicit
identity mapping. Only metadata identifies these entries as part of v2. Seed the
month once; do not also ingest the standalone morning. Seeding refuses a database
containing other dataset identities or manifest versions, including standalone
morning metadata. The historical owner dataset must remain on its existing stack.

Technical examples: July 6/21/30 late arrivals at 18:15 against an 18:00 New York
cutoff; July 2/17/28 duplicate deliveries; `CL-M2-20260707-02` unavailable transcript;
`CL-M2-20260723-04` missing inventory entry; `CL-M2-20260727-03` preserved transcript
with deliberately unavailable analysis. No dialogue is authored for the first two
unavailable inputs, and no accepted recap is supplied for either processing failure.
The exhaustive original fixture suite and explicit historical-v1 UI regression
remain separate. Dates outside July are unavailable, never verified zero.

Reproduce only in the separate internal engineering project:

```bash
export COMPOSE_PROJECT_NAME=colacci-law-slice7b
export COMPOSE_FILE=docker-compose.yml:infrastructure/local/slice7b-compose.yml
export SLICE4_RUNTIME_ROOT=/tmp/colacci-law-slice7b-runtime
export COLACCI_FIXTURE_NETWORK=colacci-law-slice7b_fixture
export COLACCI_FIXTURE_IMAGE=colacci-law-slice7b-api
docker compose build api worker web e2e
make seed-demo-month
# Equivalent explicit selection:
docker compose run --rm api python scripts/seed_demo_month.py --manifest fixtures/demo-month/manifest-v2.json
SLICE6C_EVIDENCE_DIR=/tmp/colacci-law-slice7b-check-1/evidence make test-demo-month
```

The month gate requires a new evidence directory for each attempt. It checks all
authored daily equations, every original/recap expectation, two identical seeds,
append-only review probes, full persisted-row hashes after reseeding and database/
application restart, every rendered recap across 31 dates, representative evidence
navigation, and desktop/390 px screenshots. It leaves its named stack for inspection.
Review probes are explicitly engineering assessments, not owner decisions or proof
of a completed callback. UUIDs are opaque database identities; reproducible baseline
comparison uses stable source IDs, content, daily counts, and report versions.

Dispose and reproduce only this attempt-owned dataset after retaining evidence:

```bash
docker compose down -v --remove-orphans
make seed-demo-month
# Capture its output and compare with the original seed baseline.
# Use a fresh evidence directory for another complete month gate.
```

The internal browser path remains `http://web:5173`; published host port 15175 is
not owner-launch qualification. Host-browser access remains a 7C issue. Do not
weaken isolation. The tracker alone controls readiness; 7B does not start 7C,
7D, owner review, providers, production or notifications.

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
