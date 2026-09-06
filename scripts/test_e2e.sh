#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export COMPOSE_FILE="$repository_root/docker-compose.yml:$repository_root/infrastructure/local/offline-compose.yml:$repository_root/infrastructure/local/slice5a-compose.yml"
export SLICE4_RUNTIME_ROOT="${SLICE4_RUNTIME_ROOT:-/tmp/colacci-law-e2e-runtime}"
export COLACCI_PYTHON_RUNTIME_USER="$(id -u):$(id -g)"
if [[ "$SLICE4_RUNTIME_ROOT" == "/tmp/colacci-law-slice4-local" ]]; then
  echo "Use a private disposable runtime; retained owner assets are forbidden." >&2
  exit 1
fi
if [[ -n "$(docker ps -aq --filter label=com.docker.compose.project=colacci-law-e2e)" ]]; then
  echo "Existing E2E resources must be preserved; stop and inspect them first." >&2
  exit 1
fi
umask 077

PYTHONPATH=. python3 scripts/generate_manual_upload_assets.py
evidence_directory="${SLICE4_EVIDENCE_DIR:-${SLICE2_EVIDENCE_DIR:-/tmp/colacci-law-slice2-evidence}}"
mkdir -p "$evidence_directory"
export SLICE4_EVIDENCE_DIR="$evidence_directory"
export VITE_API_BASE_URL="http://api:8000"
export CORS_ORIGINS='["http://web:5173"]'

cleanup_e2e_stack() {
  docker compose -p colacci-law-e2e --profile e2e down -v --remove-orphans >/dev/null 2>&1 || true
  PYTHONPATH=. python3 scripts/cleanup_manual_upload_assets.py >/dev/null
}
trap cleanup_e2e_stack EXIT

docker compose -p colacci-law-e2e --profile e2e build api worker web e2e
docker compose -p colacci-law-e2e up -d --wait db web
docker compose -p colacci-law-e2e run --rm api alembic upgrade head
docker compose -p colacci-law-e2e up -d --wait api worker web
docker compose -p colacci-law-e2e run --rm api python scripts/seed_demo.py
e2e_status=0
docker compose -p colacci-law-e2e --profile e2e run --rm e2e npm run test:e2e -- --project=review-flow --project=manual-upload --project=local-operations || e2e_status=$?
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
if [[ "$e2e_status" != "0" ]]; then exit "$e2e_status"; fi
unset PLAYWRIGHT_GREP
docker compose -p colacci-law-e2e run --rm api alembic downgrade base
docker compose -p colacci-law-e2e run --rm api alembic upgrade head
docker compose -p colacci-law-e2e run --rm api python scripts/seed_recovery_probe.py
docker compose -p colacci-law-e2e --profile e2e run --rm e2e npm run test:e2e -- --project=recovery-probe
docker compose -p colacci-law-e2e run --rm api alembic downgrade base
docker compose -p colacci-law-e2e run --rm api alembic upgrade head
docker compose -p colacci-law-e2e run --rm api python scripts/seed_demo_month.py --manifest fixtures/demo-month/manifest-v2.json
docker compose -p colacci-law-e2e --profile e2e run --rm -e MONTH_V2=1 e2e npm run test:e2e -- --project=morning-briefing --project=everyday-review
