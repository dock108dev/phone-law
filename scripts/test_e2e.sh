#!/usr/bin/env bash
set -euo pipefail

evidence_directory="${SLICE2_EVIDENCE_DIR:-/tmp/colacci-law-slice2-evidence}"
mkdir -p "$evidence_directory"
export VITE_API_BASE_URL="http://api:8000"
export CORS_ORIGINS='["http://web:5173"]'

restore_main_stack() {
  docker compose -p colacci-law-e2e --profile e2e down -v --remove-orphans >/dev/null 2>&1 || true
  docker compose up -d --wait db api worker web >/dev/null
}
trap restore_main_stack EXIT

docker compose down >/dev/null
docker compose -p colacci-law-e2e --profile e2e build api worker web e2e
docker compose -p colacci-law-e2e up -d --wait db web
docker compose -p colacci-law-e2e run --rm api alembic upgrade head
docker compose -p colacci-law-e2e up -d --wait api worker web
docker compose -p colacci-law-e2e run --rm api python scripts/seed_demo.py
docker compose -p colacci-law-e2e --profile e2e run --rm e2e
