#!/usr/bin/env bash
set -euo pipefail

# The generated fixtures remain private to the invoking user. Match the Python
# containers to that user so native Linux bind mounts preserve the boundary.
export COLACCI_PYTHON_RUNTIME_USER="$(id -u):$(id -g)"

PYTHONPATH=. python3 scripts/generate_manual_upload_assets.py
evidence_directory="${SLICE4_EVIDENCE_DIR:-${SLICE2_EVIDENCE_DIR:-/tmp/colacci-law-slice2-evidence}}"
mkdir -p "$evidence_directory"
export SLICE4_EVIDENCE_DIR="$evidence_directory"
export VITE_API_BASE_URL="http://api:8000"
export CORS_ORIGINS='["http://web:5173"]'

restore_main_stack() {
  docker compose -p colacci-law-e2e --profile e2e down -v --remove-orphans >/dev/null 2>&1 || true
  unset VITE_API_BASE_URL CORS_ORIGINS
  PYTHONPATH=. python3 scripts/cleanup_manual_upload_assets.py >/dev/null
  if [[ "${MANUAL_UPLOAD_OFFLINE:-0}" == "1" ]]; then
    COMPOSE_FILE=docker-compose.yml docker compose down >/dev/null 2>&1 || true
    COMPOSE_FILE=docker-compose.yml docker compose up -d --wait db >/dev/null
    COMPOSE_FILE=docker-compose.yml docker compose run --rm api alembic upgrade head >/dev/null
    COMPOSE_FILE=docker-compose.yml docker compose up -d --wait api worker web >/dev/null
  else
    docker compose up -d --wait db >/dev/null
    docker compose run --rm api alembic upgrade head >/dev/null
    docker compose up -d --wait api worker web >/dev/null
  fi
}
trap restore_main_stack EXIT

docker compose down >/dev/null
docker compose -p colacci-law-e2e --profile e2e build api worker web e2e
docker compose -p colacci-law-e2e up -d --wait db web
docker compose -p colacci-law-e2e run --rm api alembic upgrade head
docker compose -p colacci-law-e2e up -d --wait api worker web
docker compose -p colacci-law-e2e run --rm api python scripts/seed_demo.py
e2e_status=0
docker compose -p colacci-law-e2e --profile e2e run --rm e2e || e2e_status=$?
docker compose -p colacci-law-e2e logs --no-color api worker > "$evidence_directory/e2e-application.log"
docker compose -p colacci-law-e2e run --rm --no-deps \
  -v "$evidence_directory:/evidence:ro" api \
  python scripts/inspect_logs.py /evidence/e2e-application.log
if [[ "${COLLECT_SLICE4:-0}" == "1" ]]; then
  docker compose -p colacci-law-e2e run --rm --no-deps \
    -e MANUAL_UPLOAD_OFFLINE="${MANUAL_UPLOAD_OFFLINE:-0}" api \
    python scripts/collect_manual_upload_evidence.py > "$evidence_directory/database-evidence.json"
else
  docker compose -p colacci-law-e2e run --rm --no-deps api \
    python scripts/collect_slice2_evidence.py > "$evidence_directory/database-evidence.json"
fi
exit "$e2e_status"
