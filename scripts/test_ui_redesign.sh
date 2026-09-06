#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
evidence_root="${SLICE6D_EVIDENCE_DIR:-/tmp/colacci-law-slice6d/evidence}"
project_name="${COLACCI_UI_PROJECT:-colacci-law-slice6d-ui}"
runtime_root="${SLICE4_RUNTIME_ROOT:-/tmp/colacci-law-ui-runtime}"
export SLICE4_RUNTIME_ROOT="$runtime_root"

export COMPOSE_FILE="$repository_root/docker-compose.yml:$repository_root/infrastructure/local/slice6d-compose.yml:$repository_root/infrastructure/local/offline-compose.yml"
export SLICE4_EVIDENCE_DIR="$evidence_root"
export VITE_API_BASE_URL=""
export VITE_API_PROXY_TARGET="http://api:8000"
export CORS_ORIGINS='["http://web:5173"]'
export INCLUDE_UI_REDESIGN=1

umask 077
cd "$repository_root"

source "$repository_root/scripts/campaign_resources.sh"
campaign_claim
cleanup_stack() { campaign_cleanup; }
trap cleanup_stack EXIT
mkdir -p "$evidence_root/before" "$evidence_root/after"

docker compose -p "$project_name" --profile e2e build api web e2e
docker compose -p "$project_name" up -d --wait db
docker compose -p "$project_name" run --rm api alembic upgrade head
docker compose -p "$project_name" run --rm api python scripts/seed_demo_month.py --manifest fixtures/demo-month/manifest.json > "$evidence_root/seed-result.json"
docker compose -p "$project_name" up -d --wait api web
docker compose -p "$project_name" --profile e2e run --rm e2e npm run test:e2e -- --project=ui-redesign
docker compose -p "$project_name" run --rm api alembic downgrade base
docker compose -p "$project_name" run --rm api alembic upgrade head
docker compose -p "$project_name" run --rm api python scripts/seed_demo_month.py --manifest fixtures/demo-month/manifest-v2.json > "$evidence_root/morning-seed.json"
docker compose -p "$project_name" --profile e2e run --rm -e MONTH_V2=1 e2e npm run test:e2e -- --project=morning-briefing --project=everyday-review
docker compose -p "$project_name" logs --no-color api worker > "$evidence_root/application.log"
docker compose -p "$project_name" run --rm --no-deps -v "$evidence_root:/evidence:ro" api python scripts/inspect_logs.py /evidence/application.log
docker compose -p "$project_name" run --rm --no-deps api python scripts/secret_scan.py > "$evidence_root/secret-scan.txt"
docker compose -p "$project_name" run --rm --no-deps --user root \
  -v "$evidence_root:/evidence" \
  api sh -c 'find /evidence -type d -exec chmod 700 {} \; && find /evidence -type f -exec chmod 600 {} \;'

trap - EXIT
cleanup_stack
echo "ui-redesign routes=passed responsive=passed accessibility=passed recovery=passed external_requests=0"
