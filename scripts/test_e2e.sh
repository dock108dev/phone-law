#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export COMPOSE_FILE="$repository_root/docker-compose.yml:$repository_root/infrastructure/local/offline-compose.yml:$repository_root/infrastructure/local/slice5a-compose.yml"
export SLICE4_RUNTIME_ROOT="${SLICE4_RUNTIME_ROOT:-/tmp/colacci-law-e2e-runtime}"
export COLACCI_PYTHON_RUNTIME_USER="$(id -u):$(id -g)"
umask 077
project_name="${COLACCI_E2E_PROJECT:-colacci-law-e2e}"
runtime_root="$SLICE4_RUNTIME_ROOT"
evidence_root="${SLICE4_EVIDENCE_DIR:-${SLICE2_EVIDENCE_DIR:-/tmp/colacci-law-slice2-evidence}}"
evidence_directory="$evidence_root"
export SLICE4_EVIDENCE_DIR="$evidence_root"
source "$repository_root/scripts/campaign_resources.sh"
campaign_claim
trap campaign_cleanup EXIT
PYTHONPATH=. python3 scripts/generate_manual_upload_assets.py
export VITE_API_BASE_URL="http://api:8000"
export CORS_ORIGINS='["http://web:5173"]'

docker compose -p "$project_name" --profile e2e build api worker web e2e
docker compose -p "$project_name" up -d --wait db web
docker compose -p "$project_name" run --rm api alembic upgrade head
docker compose -p "$project_name" up -d --wait api worker web
docker compose -p "$project_name" run --rm api python scripts/seed_demo.py
e2e_status=0
docker compose -p "$project_name" --profile e2e run --rm e2e npm run test:e2e -- --project=review-flow --project=manual-upload --project=local-operations || e2e_status=$?
docker compose -p "$project_name" logs --no-color api worker > "$evidence_directory/e2e-application.log"
docker compose -p "$project_name" run --rm --no-deps \
  -v "$evidence_directory:/evidence:ro" api \
  python scripts/inspect_logs.py /evidence/e2e-application.log
if [[ "${COLLECT_SLICE4:-0}" == "1" ]]; then
  docker compose -p "$project_name" run --rm --no-deps \
    -e MANUAL_UPLOAD_OFFLINE="${MANUAL_UPLOAD_OFFLINE:-0}" api \
    python scripts/collect_manual_upload_evidence.py > "$evidence_directory/database-evidence.json"
else
  docker compose -p "$project_name" run --rm --no-deps api \
    python scripts/collect_slice2_evidence.py > "$evidence_directory/database-evidence.json"
fi
if [[ "$e2e_status" != "0" ]]; then exit "$e2e_status"; fi
unset PLAYWRIGHT_GREP
docker compose -p "$project_name" run --rm api alembic downgrade base
docker compose -p "$project_name" run --rm api alembic upgrade head
docker compose -p "$project_name" run --rm api python scripts/seed_recovery_probe.py
docker compose -p "$project_name" --profile e2e run --rm e2e npm run test:e2e -- --project=recovery-probe
docker compose -p "$project_name" run --rm api alembic downgrade base
docker compose -p "$project_name" run --rm api alembic upgrade head
docker compose -p "$project_name" run --rm api python scripts/seed_demo_month.py --manifest fixtures/demo-month/manifest-v2.json
docker compose -p "$project_name" --profile e2e run --rm -e MONTH_V2=1 e2e npm run test:e2e -- --project=morning-briefing --project=everyday-review
