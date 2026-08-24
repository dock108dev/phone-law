#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export COMPOSE_FILE="$repository_root/docker-compose.yml:$repository_root/infrastructure/local/offline-compose.yml"
export SLICE4_EVIDENCE_DIR="/tmp/colacci-law-slice4-local/evidence"
export PLAYWRIGHT_GREP="manual upload"
export COLLECT_SLICE4="1"
export MANUAL_UPLOAD_OFFLINE="1"
export COLACCI_PYTHON_RUNTIME_USER="$(id -u):$(id -g)"

cd "$repository_root"

cleanup_manual_stack() {
  docker compose -p colacci-law-manual down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup_manual_stack EXIT

PYTHONPATH=. python3 scripts/generate_manual_upload_assets.py
docker compose -p colacci-law-manual up -d --wait db
docker compose -p colacci-law-manual exec -T db psql -v ON_ERROR_STOP=1 \
  -U colacci_demo -d postgres -f /docker-entrypoint-initdb.d/001-init-databases.sql
docker compose -p colacci-law-manual run --rm \
  -e APP_PROFILE=test \
  -e DATABASE_URL=postgresql+psycopg://colacci_demo:local-demo-only-password@db:5432/colacci_test \
  api /bin/bash -c 'alembic downgrade base && alembic upgrade head && pytest -q tests/unit/test_manual_upload.py tests/unit/test_transcript_import.py tests/integration/test_manual_upload_full_loop.py'
mkdir -p "$SLICE4_EVIDENCE_DIR"
PYTHONPATH=. python3 scripts/collect_manual_upload_validation_evidence.py \
  > "$SLICE4_EVIDENCE_DIR/validation-evidence.json"
cleanup_manual_stack
./scripts/test_e2e.sh
echo "manual-upload-focused python=passed browser=1 network=none"
