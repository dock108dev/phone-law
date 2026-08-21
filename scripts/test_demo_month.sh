#!/usr/bin/env bash
set -euo pipefail

evidence_directory="${SLICE6C_EVIDENCE_DIR:-/tmp/colacci-law-slice6c/evidence}"
mkdir -p "$evidence_directory"
chmod 0700 "$(dirname "$evidence_directory")" "$evidence_directory"
export SLICE6C_EVIDENCE_DIR="$evidence_directory"

docker compose up -d --wait db
docker compose run --rm api alembic upgrade head
docker compose run --rm api python scripts/seed_demo_month.py > "$evidence_directory/seed-run-1.json"
docker compose run --rm api python scripts/seed_demo_month.py > "$evidence_directory/seed-run-2.json"
cmp "$evidence_directory/seed-run-1.json" "$evidence_directory/seed-run-2.json"
docker compose run --rm -e SLICE6C_EVIDENCE_DIR=/evidence -v "$evidence_directory:/evidence" api python scripts/test_demo_month.py > "$evidence_directory/test-output.json"
export VITE_API_BASE_URL="http://api:8000"
export CORS_ORIGINS='["http://web:5173"]'
docker compose up -d --wait --force-recreate api web
docker compose restart api web >/dev/null
docker compose up -d --wait api web
docker compose run --rm -e SLICE6C_EVIDENCE_DIR=/evidence -v "$evidence_directory:/evidence" api python scripts/test_demo_month.py > "$evidence_directory/restart-persistence.json"
docker compose --profile e2e build e2e
PLAYWRIGHT_GREP="July month history" INCLUDE_DEMO_MONTH=1 SLICE4_EVIDENCE_DIR="$evidence_directory" docker compose --profile e2e run --rm e2e
docker compose logs --no-color api worker > "$evidence_directory/application.log"
docker compose run --rm --no-deps -v "$evidence_directory:/evidence:ro" api python scripts/inspect_logs.py /evidence/application.log
docker compose run --rm --no-deps api python scripts/secret_scan.py > "$evidence_directory/secret-scan.txt"
chmod 0600 "$evidence_directory"/*
cmp "$evidence_directory/test-output.json" "$evidence_directory/restart-persistence.json"
docker compose run --rm --no-deps -e SLICE6C_EVIDENCE_DIR=/evidence -v "$evidence_directory:/evidence" api python scripts/finalize_demo_month_evidence.py
