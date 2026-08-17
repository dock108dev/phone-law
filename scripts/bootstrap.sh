#!/usr/bin/env bash
set -euo pipefail

docker compose build
docker compose up -d --wait db
docker compose exec -T db psql \
  -v ON_ERROR_STOP=1 \
  -U colacci_demo \
  -d postgres \
  -f /docker-entrypoint-initdb.d/001-init-databases.sql
docker compose run --rm api alembic upgrade head

echo "Bootstrap complete: images built, PostgreSQL ready, and migration applied."
