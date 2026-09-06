#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export COMPOSE_FILE="$repository_root/docker-compose.yml:$repository_root/infrastructure/local/offline-compose.yml:$repository_root/infrastructure/local/slice5a-compose.yml"
export SLICE4_EVIDENCE_DIR="${SLICE4_EVIDENCE_DIR:-/tmp/colacci-law-manual-evidence}"
export SLICE4_RUNTIME_ROOT="${SLICE4_RUNTIME_ROOT:-/tmp/colacci-law-manual-runtime}"
export PLAYWRIGHT_GREP="manual upload"
export COLLECT_SLICE4="1"
export MANUAL_UPLOAD_OFFLINE="1"
export COLACCI_PYTHON_RUNTIME_USER="$(id -u):$(id -g)"

cd "$repository_root"

project_name="${COLACCI_MANUAL_PROJECT:-colacci-law-manual}"
runtime_root="$SLICE4_RUNTIME_ROOT"
evidence_root="$SLICE4_EVIDENCE_DIR"
source "$repository_root/scripts/campaign_resources.sh"
campaign_claim
trap campaign_cleanup EXIT

PYTHONPATH=. python3 scripts/generate_manual_upload_assets.py
docker compose -p "$project_name" build api
docker compose -p "$project_name" up -d --wait db
docker compose -p "$project_name" exec -T db psql -v ON_ERROR_STOP=1 \
  -U colacci_demo -d postgres -f /docker-entrypoint-initdb.d/001-init-databases.sql
docker compose -p "$project_name" run --rm \
  -e APP_PROFILE=test \
  -e DATABASE_URL=postgresql+psycopg://colacci_demo:local-demo-only-password@db:5432/colacci_test \
  api /bin/bash -c 'alembic downgrade base && alembic upgrade head && pytest -q tests/unit/test_manual_upload.py tests/unit/test_transcript_import.py tests/integration/test_manual_upload_full_loop.py'
mkdir -p "$SLICE4_EVIDENCE_DIR"
PYTHONPATH=. python3 scripts/collect_manual_upload_validation_evidence.py \
  > "$SLICE4_EVIDENCE_DIR/validation-evidence.json"
campaign_cleanup
trap - EXIT
SLICE4_EVIDENCE_DIR="$evidence_root/browser" ./scripts/test_e2e.sh
echo "manual-upload-focused python=passed browser=1 network=none"
