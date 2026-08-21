#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
evidence_root="/tmp/colacci-law-slice5a/evidence"
runtime_root="/tmp/colacci-law-slice5a/runtime"
project_name="colacci-law-slice5a-proof"

export COMPOSE_FILE="$repository_root/docker-compose.yml:$repository_root/infrastructure/local/offline-compose.yml:$repository_root/infrastructure/local/slice5a-compose.yml"
export SLICE4_EVIDENCE_DIR="$evidence_root"
export SLICE4_RUNTIME_ROOT="$runtime_root"
export VITE_API_BASE_URL="http://api:8000"
export CORS_ORIGINS='["http://web:5173"]'

umask 077
cd "$repository_root"

remove_runtime() {
  if [[ "$runtime_root" == "/tmp/colacci-law-slice5a/runtime" ]]; then
    rm -rf -- "$runtime_root"
  fi
}

cleanup_stack() {
  docker compose -p "$project_name" --profile e2e down -v --remove-orphans >/dev/null 2>&1 || true
  remove_runtime
}
trap cleanup_stack EXIT

cleanup_stack
mkdir -p "$evidence_root" "$runtime_root"
chmod 700 "/tmp/colacci-law-slice5a" "$evidence_root" "$runtime_root"

# Image preparation is outside the focused proof. Every execution below uses
# an internal Docker network or no network at all.
docker compose -p "$project_name" --profile e2e build api web e2e

docker compose -p "$project_name" up -d --wait db
docker compose -p "$project_name" exec -T db psql -v ON_ERROR_STOP=1 \
  -U colacci_demo -d postgres -f /docker-entrypoint-initdb.d/001-init-databases.sql
docker compose -p "$project_name" run --rm \
  -e APP_PROFILE=test \
  -e DATABASE_URL=postgresql+psycopg://colacci_demo:local-demo-only-password@db:5432/colacci_test \
  api /bin/bash -c 'alembic downgrade base && alembic upgrade head'
docker compose -p "$project_name" run --rm --no-deps api \
  pytest -q -m 'not integration'
docker compose -p "$project_name" run --rm \
  -e APP_PROFILE=test \
  -e DATABASE_URL=postgresql+psycopg://colacci_demo:local-demo-only-password@db:5432/colacci_test \
  api pytest -q \
  tests/integration/test_local_operations.py \
  tests/integration/test_migration_and_readiness.py

docker compose -p "$project_name" run --rm api alembic upgrade head
docker compose -p "$project_name" up -d --wait api web
docker compose -p "$project_name" run --rm api python scripts/seed_demo.py >/dev/null
docker compose -p "$project_name" --profile e2e run --rm e2e \
  npm run test:e2e -- --project=local-operations
docker compose -p "$project_name" logs --no-color api > "$evidence_root/operations-application.log"
docker run --rm --network none \
  -v "$evidence_root:/evidence:ro" \
  -e PYTHONPATH=/workspace \
  -w /workspace \
  "$project_name-api:latest" \
  python scripts/inspect_logs.py /evidence/operations-application.log
docker compose -p "$project_name" run --rm \
  -v "$evidence_root:/tmp/colacci-law-slice5a/evidence" \
  api \
  python scripts/collect_local_operations_evidence.py
docker run --rm --network none \
  -v "$repository_root:/workspace:ro" \
  -e PYTHONPATH=/workspace \
  -w /workspace \
  "$project_name-api:latest" \
  python scripts/secret_scan.py

docker compose -p "$project_name" --profile e2e down -v --remove-orphans
remove_runtime
if [[ -n "$(docker ps -q --filter "label=com.docker.compose.project=$project_name")" ]]; then
  echo "disposable stack cleanup failed" >&2
  exit 1
fi
if [[ -e "$runtime_root" ]]; then
  echo "disposable runtime cleanup failed" >&2
  exit 1
fi
PYTHONPATH=. python3 scripts/finalize_local_operations_evidence.py
trap - EXIT

echo "local-operations python=passed browser=passed accessibility=passed network=none cleanup=passed"
