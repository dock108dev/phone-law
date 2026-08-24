#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
acceptance_root="/tmp/colacci-law-slice6a"
evidence_root="$acceptance_root/evidence"
runtime_root="/tmp/colacci-law-slice4-local"
project_name="colacci-law-slice6a-proof"

export COMPOSE_FILE="$repository_root/docker-compose.yml:$repository_root/infrastructure/local/offline-compose.yml:$repository_root/infrastructure/local/slice5a-compose.yml:$repository_root/infrastructure/local/slice6a-compose.yml"
export SLICE4_EVIDENCE_DIR="$evidence_root"
export SLICE4_RUNTIME_ROOT="$runtime_root"
export VITE_API_BASE_URL="http://api:8000"
export CORS_ORIGINS='["http://web:5173"]'
export COLACCI_PYTHON_RUNTIME_USER="$(id -u):$(id -g)"

umask 077
cd "$repository_root"

if [[ "${COLACCI_ALLOW_DIRTY:-0}" != "1" && -n "$(git status --short)" ]]; then
  echo "local acceptance requires a clean tracked checkout" >&2
  exit 1
fi
if [[ "$(git merge-base HEAD 22710801be61a3f97825fbc36fb3d0e0e92f8dbc)" != "22710801be61a3f97825fbc36fb3d0e0e92f8dbc" ]]; then
  echo "local acceptance source commit is not an ancestor" >&2
  exit 1
fi
current_branch="$(git branch --show-current)"
if [[ "$current_branch" != "codex/slice-6a-local-acceptance" && "$current_branch" != "codex/slice-3b-final-preflight" && "$current_branch" != "codex/slice-6c-demo-month" && "$current_branch" != "codex/slice-6d-firm-ui" ]]; then
  echo "local acceptance must run on an accepted local-product descendant branch" >&2
  exit 1
fi

cleanup_stack() {
  docker compose -p "$project_name" --profile e2e down -v --remove-orphans >/dev/null 2>&1 || true
}
cleanup_runtime() {
  if [[ "$runtime_root" == "/tmp/colacci-law-slice4-local" ]]; then
    rm -rf -- "$runtime_root"
  fi
}
cleanup_all() {
  cleanup_stack
  cleanup_runtime
}
trap cleanup_all EXIT

cleanup_all
rm -rf -- "$acceptance_root"
mkdir -p "$evidence_root"
chmod 700 "$acceptance_root" "$evidence_root"

# Bootstrap is a required preceding command. Reuse its local images without a
# registry, package-manager, or provider request during the measured rehearsal.
for image_name in colacci-law-api:latest colacci-law-worker:latest colacci-law-web:latest colacci-law-e2e:latest; do
  docker image inspect "$image_name" >/dev/null
done
docker tag colacci-law-api:latest "$project_name-api:latest"
docker tag colacci-law-worker:latest "$project_name-worker:latest"
docker tag colacci-law-web:latest "$project_name-web:latest"
docker tag colacci-law-e2e:latest "$project_name-e2e:latest"

run_rehearsal() {
  local run_number="$1"
  cleanup_stack
  cleanup_runtime
  PYTHONPATH=. python3 scripts/generate_manual_upload_assets.py >/dev/null
  docker compose -p "$project_name" up -d --wait db
  docker compose -p "$project_name" exec -T db psql -v ON_ERROR_STOP=1 \
    -U colacci_demo -d postgres -f /docker-entrypoint-initdb.d/001-init-databases.sql >/dev/null
  docker compose -p "$project_name" run --rm api alembic upgrade head >/dev/null
  docker compose -p "$project_name" up -d --wait api worker web
  docker compose -p "$project_name" run --rm api python scripts/seed_demo.py >/dev/null
  docker compose -p "$project_name" --profile e2e run --rm \
    -e INCLUDE_LOCAL_ACCEPTANCE=1 e2e \
    npm run test:e2e -- --project=local-acceptance

  docker compose -p "$project_name" stop api worker web >/dev/null
  docker compose -p "$project_name" up -d --wait api worker web
  docker compose -p "$project_name" --profile e2e run --rm \
    -e INCLUDE_LOCAL_ACCEPTANCE=1 e2e \
    npm run test:e2e -- --project=local-acceptance-restart

  docker compose -p "$project_name" run --rm -v "$evidence_root:$evidence_root" api \
    python scripts/collect_local_acceptance_evidence.py
  docker compose -p "$project_name" run --rm \
    -e COLACCI_EVIDENCE_ROOT="$evidence_root" \
    -e COLACCI_ACCEPTANCE_SLICE=6A \
    -v "$evidence_root:$evidence_root" api \
    python scripts/collect_local_operations_evidence.py
  docker compose -p "$project_name" logs --no-color api worker > "$evidence_root/acceptance-application.log"
  docker run --rm --network none -v "$evidence_root:/evidence:ro" -e PYTHONPATH=/workspace \
    -w /workspace "$project_name-api:latest" \
    python scripts/inspect_logs.py /evidence/acceptance-application.log >/dev/null
  rm -f -- "$evidence_root/acceptance-application.log"
  cp "$evidence_root/scenario-and-reconciliation.json" "$acceptance_root/run-$run_number-scenario-and-reconciliation.json"
  cp "$evidence_root/retention-deletion.json" "$acceptance_root/run-$run_number-retention-deletion.json"
  cp "$evidence_root/backup-restore.json" "$acceptance_root/run-$run_number-backup-restore.json"
  mkdir -p "$acceptance_root/run-$run_number"
  cp "$acceptance_root/run-$run_number-scenario-and-reconciliation.json" "$acceptance_root/run-$run_number/scenario-and-reconciliation.json"
  cp "$acceptance_root/run-$run_number-retention-deletion.json" "$acceptance_root/run-$run_number/retention-deletion.json"
  cp "$acceptance_root/run-$run_number-backup-restore.json" "$acceptance_root/run-$run_number/backup-restore.json"
}

run_rehearsal 1
run_rehearsal 2

PYTHONPATH=. python3 scripts/compare_local_acceptance_runs.py \
  "$acceptance_root/run-1" "$acceptance_root/run-2" "$evidence_root/determinism.json"
rm -rf -- "$acceptance_root/run-1" "$acceptance_root/run-2"
rm -f -- "$acceptance_root"/run-*-scenario-and-reconciliation.json \
  "$acceptance_root"/run-*-retention-deletion.json \
  "$acceptance_root"/run-*-backup-restore.json
docker run --rm --network none -v "$repository_root:/workspace:ro" -e PYTHONPATH=/workspace \
  -w /workspace "$project_name-api:latest" python scripts/secret_scan.py >/dev/null

cleanup_all
if [[ -n "$(docker ps -q --filter "label=com.docker.compose.project=$project_name")" ]]; then
  echo "disposable acceptance stack cleanup failed" >&2
  exit 1
fi
if [[ -e "$runtime_root" ]]; then
  echo "generated acceptance media cleanup failed" >&2
  exit 1
fi

PYTHONPATH=. python3 scripts/write_local_acceptance_cleanup_evidence.py
PYTHONPATH=. python3 scripts/finalize_local_acceptance_evidence.py
trap - EXIT

echo "local-acceptance runs=2 roles=3 reconciliation=exact accessibility=passed network=none cleanup=passed decision=accepted-locally"
