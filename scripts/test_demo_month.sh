#!/usr/bin/env bash
set -euo pipefail

evidence_directory="${SLICE6C_EVIDENCE_DIR:-/tmp/colacci-law-slice7b-month/evidence}"
mkdir -p "$evidence_directory"
chmod 0700 "$(dirname "$evidence_directory")" "$evidence_directory"
export SLICE6C_EVIDENCE_DIR="$evidence_directory"

# This gate must never operate on retained owner resources.
if [[ "${COMPOSE_PROJECT_NAME:-colacci-law}" == "colacci-law" ]]; then
  echo "Set a separately named disposable COMPOSE_PROJECT_NAME and isolated COMPOSE_FILE." >&2
  exit 1
fi
if [[ -e "$evidence_directory/seed-run-1.json" ]]; then
  echo "Evidence directory already used; retain it and choose a fresh attempt directory." >&2
  exit 1
fi
docker compose up -d --wait db
docker compose run --rm api alembic upgrade head
docker compose run --rm api python scripts/seed_demo_month.py > "$evidence_directory/seed-run-1.json"
docker compose run --rm api python scripts/seed_demo_month.py > "$evidence_directory/seed-run-2.json"
cmp "$evidence_directory/seed-run-1.json" "$evidence_directory/seed-run-2.json"
docker compose run --rm -e SLICE6C_EVIDENCE_DIR=/evidence/initial -v "$evidence_directory:/evidence" api python scripts/test_demo_month.py > "$evidence_directory/test-output.json"
docker compose run --rm api python scripts/snapshot_demo_month.py --add-review > "$evidence_directory/persisted-before.json"
docker compose run --rm api python scripts/seed_demo_month.py > "$evidence_directory/seed-with-review.json"
docker compose run --rm api python scripts/snapshot_demo_month.py > "$evidence_directory/persisted-reseed.json"
cmp "$evidence_directory/persisted-before.json" "$evidence_directory/persisted-reseed.json"
export VITE_API_BASE_URL="http://api:8000"
export CORS_ORIGINS='["http://web:5173"]'
docker compose up -d --wait --force-recreate api web
docker compose restart db api web >/dev/null
docker compose up -d --wait api web
docker compose run --rm api python scripts/snapshot_demo_month.py > "$evidence_directory/persisted-restart.json"
cmp "$evidence_directory/persisted-before.json" "$evidence_directory/persisted-restart.json"
docker compose run --rm -e SLICE6C_EVIDENCE_DIR=/evidence/restarted -v "$evidence_directory:/evidence" api python scripts/test_demo_month.py > "$evidence_directory/restart-persistence.json"
INCLUDE_DEMO_MONTH=1 SLICE4_EVIDENCE_DIR="$evidence_directory" docker compose --profile e2e run --rm -e MONTH_V2=1 e2e npm run test:e2e -- --project=demo-month --project=morning-briefing --project=everyday-review
docker compose logs --no-color api worker > "$evidence_directory/application.log"
docker compose run --rm --no-deps -v "$evidence_directory:/evidence:ro" api python scripts/inspect_logs.py /evidence/application.log
docker compose run --rm --no-deps api python scripts/secret_scan.py > "$evidence_directory/secret-scan.txt"
find "$evidence_directory" -type d -exec chmod 0700 {} +
find "$evidence_directory" -type f -exec chmod 0600 {} +
docker compose run --rm --no-deps -e SLICE6C_EVIDENCE_DIR=/evidence -v "$evidence_directory:/evidence" api python scripts/finalize_demo_month_evidence.py
