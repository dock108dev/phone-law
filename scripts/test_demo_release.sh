#!/usr/bin/env bash
set -euo pipefail
export COLACCI_RELEASE=1
export SLICE6C_EVIDENCE_DIR="${SLICE6C_EVIDENCE_DIR:-/tmp/colacci-law-slice6e/evidence}"
exec "$(dirname "${BASH_SOURCE[0]}")/test_demo_month.sh"
