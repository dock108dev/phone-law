#!/usr/bin/env bash
set -euo pipefail

docker compose up -d --wait db
docker compose run --rm api alembic upgrade head
docker compose up -d --wait api worker web
docker compose ps

echo "Local application ready at http://localhost:15173"
