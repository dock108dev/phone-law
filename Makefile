SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE := docker compose
PY_RUN := $(COMPOSE) run --rm --no-deps api
WEB_RUN := $(COMPOSE) run --rm --no-deps web

.PHONY: help bootstrap prepare-candidate-images seed-demo seed-demo-month dev stop clean generate-contract-schemas generate-test-audio test-audio test-manual-upload test-local-operations test-local-acceptance test-demo-month test-demo-release test-ui-redesign lint typecheck test test-integration test-fixtures test-e2e build smoke audit secret-scan logs

help:
	@printf '%s\n' \
		"Stable commands:" \
		"  bootstrap  prepare-candidate-images  seed-demo  seed-demo-month  dev  stop  clean" \
		"  generate-contract-schemas  generate-test-audio" \
		"  lint  typecheck  test  test-integration  test-fixtures  test-e2e  build  smoke  audit" \
		"  test-audio" \
		"  test-manual-upload  test-local-operations  test-local-acceptance" \
		"  test-demo-month  test-demo-release  test-ui-redesign  secret-scan  logs"

bootstrap:
	./scripts/bootstrap.sh

seed-demo:
	$(COMPOSE) up -d --wait db
	$(COMPOSE) run --rm api alembic upgrade head
	$(COMPOSE) run --rm api python scripts/seed_demo.py

seed-demo-month:
	$(COMPOSE) up -d --wait db
	$(COMPOSE) run --rm api alembic upgrade head
	$(COMPOSE) run --rm api python scripts/seed_demo_month.py

test-demo-month:
	./scripts/test_demo_month.sh

prepare-candidate-images:
	COLACCI_CANDIDATE_EVIDENCE_DIR="$${COLACCI_CANDIDATE_EVIDENCE_DIR:-/tmp/colacci-law-candidate/evidence}" PYTHONPATH=. python3 scripts/prepare_candidate_images.py

test-demo-release:
	./scripts/test_demo_release.sh

test-ui-redesign:
	./scripts/test_ui_redesign.sh

dev:
	./scripts/dev.sh

stop:
	$(COMPOSE) down

clean:
	./scripts/clean-local.sh

generate-contract-schemas:
	$(COMPOSE) run --rm --no-deps --user "$$(id -u):$$(id -g)" -v "$(CURDIR):/source:rw" -w /source -e PYTHONPATH=/source api python scripts/generate_contract_schemas.py

generate-test-audio:
	PYTHONPATH=. python3 scripts/generate_test_audio.py

test-audio: generate-test-audio
	$(COMPOSE) run --rm --no-deps --user root -v "$${COLACCI_SYNTHETIC_ROOT:-/tmp/colacci-law-slice3a}:/tmp/colacci-law-slice3a" api python scripts/test_audio_boundary.py

test-manual-upload:
	./scripts/test_manual_upload.sh

test-local-operations:
	./scripts/test_local_operations.sh

test-local-acceptance:
	./scripts/test_local_acceptance.sh

lint:
	$(PY_RUN) ruff format --check apps packages scripts tests
	$(PY_RUN) ruff check apps packages scripts tests
	$(PY_RUN) bandit -q -c pyproject.toml -r apps packages scripts
	$(PY_RUN) python scripts/verify_dependency_pins.py
	$(PY_RUN) python scripts/generate_contract_schemas.py --check
	$(PY_RUN) python scripts/secret_scan.py
	$(WEB_RUN) npm run lint

typecheck:
	$(PY_RUN) mypy apps packages scripts
	$(WEB_RUN) npm run typecheck

test:
	$(PY_RUN) pytest -m "not integration" --cov --cov-report=term-missing
	$(WEB_RUN) npm test -- --run

test-integration: export COLACCI_PYTHON_RUNTIME_USER := $(shell id -u):$(shell id -g)
test-integration:
	PYTHONPATH=. python3 scripts/generate_manual_upload_assets.py
	$(COMPOSE) up -d --wait db
	$(COMPOSE) exec -T db psql -v ON_ERROR_STOP=1 -U colacci_demo -d postgres -f /docker-entrypoint-initdb.d/001-init-databases.sql
	$(COMPOSE) run --rm -e APP_PROFILE=test -e DATABASE_URL=postgresql+psycopg://colacci_demo:local-demo-only-password@db:5432/colacci_test api pytest -m integration

test-fixtures:
	$(COMPOSE) up -d --wait db
	$(COMPOSE) exec -T db psql -v ON_ERROR_STOP=1 -U colacci_demo -d postgres -f /docker-entrypoint-initdb.d/001-init-databases.sql
	docker run --rm --network $${COLACCI_FIXTURE_NETWORK:-colacci-law_fixture} -v "$(CURDIR):/workspace:ro" -v "$${COLACCI_FIXTURE_REPORT_ROOT:-/tmp/colacci-law-fixtures}:/tmp/colacci-law-fixtures" -w /workspace -e APP_PROFILE=test -e DATABASE_URL=postgresql+psycopg://colacci_demo:local-demo-only-password@db:5432/colacci_test -e PYTHONPATH=/workspace $${COLACCI_FIXTURE_IMAGE:-colacci-law-api:latest} python scripts/evaluate_fixtures.py

test-e2e:
	./scripts/test_e2e.sh

build:
	$(WEB_RUN) npm run build

smoke:
	$(COMPOSE) run --rm api python scripts/smoke.py

audit:
	$(PY_RUN) pip-audit --require-hashes -r requirements.lock
	$(WEB_RUN) npm audit --audit-level=high

secret-scan:
	$(PY_RUN) python scripts/secret_scan.py

logs:
	$(COMPOSE) logs --no-color api worker
