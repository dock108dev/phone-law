#!/usr/bin/env bash
set -euo pipefail

if [[ "${CONFIRM_LOCAL_DATA_DELETE:-}" != "yes" ]]; then
  echo "Refusing to delete the local database volume."
  echo "Run CONFIRM_LOCAL_DATA_DELETE=yes make clean for a clean synthetic-only reset."
  exit 2
fi

docker compose down --volumes --remove-orphans
echo "Local synthetic services and the local PostgreSQL volume were removed."
