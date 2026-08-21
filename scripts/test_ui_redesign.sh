#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
evidence_root="${SLICE6D_EVIDENCE_DIR:-/tmp/colacci-law-slice6d/evidence}"
project_name="colacci-law-slice6d-ui"

export COMPOSE_FILE="$repository_root/docker-compose.yml:$repository_root/infrastructure/local/slice6d-compose.yml"
export SLICE4_EVIDENCE_DIR="$evidence_root"
export VITE_API_BASE_URL=""
export VITE_API_PROXY_TARGET="http://api:8000"
export CORS_ORIGINS='["http://web:5173"]'
export INCLUDE_UI_REDESIGN=1

umask 077
cd "$repository_root"

cleanup_stack() {
  docker compose -p "$project_name" --profile e2e down -v --remove-orphans --rmi local >/dev/null 2>&1 || true
  docker builder prune -af >/dev/null 2>&1 || true
}
trap cleanup_stack EXIT

cleanup_stack
mkdir -p "$evidence_root/before" "$evidence_root/after"
chmod 700 "$(dirname "$evidence_root")" "$evidence_root" "$evidence_root/before" "$evidence_root/after"

docker compose -p "$project_name" --profile e2e build api web e2e
docker compose -p "$project_name" up -d --wait db
docker compose -p "$project_name" run --rm api alembic upgrade head
docker compose -p "$project_name" run --rm api python scripts/seed_demo_month.py > "$evidence_root/seed-result.json"
docker compose -p "$project_name" up -d --wait api web
docker compose -p "$project_name" --profile e2e run --rm e2e npm run test:e2e -- --project=ui-redesign
docker compose -p "$project_name" logs --no-color api worker > "$evidence_root/application.log"
docker compose -p "$project_name" run --rm --no-deps -v "$evidence_root:/evidence:ro" api python scripts/inspect_logs.py /evidence/application.log
docker compose -p "$project_name" run --rm --no-deps api python scripts/secret_scan.py > "$evidence_root/secret-scan.txt"
docker compose -p "$project_name" run --rm --no-deps --user root \
  -v "$evidence_root:/evidence" \
  api sh -c 'chmod 600 /evidence/* /evidence/before/* /evidence/after/*'

trap - EXIT
cleanup_stack
echo "ui-redesign routes=passed responsive=passed accessibility=passed recovery=passed external_requests=0"
