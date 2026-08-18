SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE := docker compose
PY_RUN := $(COMPOSE) run --rm --no-deps api
WEB_RUN := $(COMPOSE) run --rm --no-deps web

.PHONY: help bootstrap seed-demo dev stop clean generate-test-audio test-audio test-transcription-contract lint typecheck test test-integration test-fixtures test-e2e smoke audit secret-scan logs

help:
	@echo "Stable commands: bootstrap generate-test-audio test-audio test-transcription-contract seed-demo dev lint typecheck test test-integration test-fixtures test-e2e smoke"

bootstrap:
	./scripts/bootstrap.sh

seed-demo:
	$(COMPOSE) up -d --wait db
	$(COMPOSE) run --rm api alembic upgrade head
	$(COMPOSE) run --rm api python scripts/seed_demo.py

dev:
	./scripts/dev.sh

stop:
	$(COMPOSE) down

clean:
	./scripts/clean-local.sh

generate-test-audio:
	python3 scripts/generate_test_audio.py

test-audio: generate-test-audio
	$(COMPOSE) run --rm --no-deps --user root -v /tmp/colacci-law-slice3a:/tmp/colacci-law-slice3a api python scripts/test_audio_boundary.py

test-transcription-contract: generate-test-audio
	$(COMPOSE) run --rm --no-deps --user root -v /tmp/colacci-law-slice3a:/tmp/colacci-law-slice3a api python scripts/test_transcription_contract.py

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

test-integration:
	$(COMPOSE) up -d --wait db
	$(COMPOSE) exec -T db psql -v ON_ERROR_STOP=1 -U colacci_demo -d postgres -f /docker-entrypoint-initdb.d/001-init-databases.sql
	$(COMPOSE) run --rm -e APP_PROFILE=test -e DATABASE_URL=postgresql+psycopg://colacci_demo:local-demo-only-password@db:5432/colacci_test api pytest -m integration

test-fixtures:
	$(COMPOSE) up -d --wait db
	$(COMPOSE) exec -T db psql -v ON_ERROR_STOP=1 -U colacci_demo -d postgres -f /docker-entrypoint-initdb.d/001-init-databases.sql
	docker run --rm --network colacci-law_fixture -v "$(CURDIR):/workspace:ro" -v /tmp/colacci-law-fixtures:/tmp/colacci-law-fixtures -w /workspace -e APP_PROFILE=test -e DATABASE_URL=postgresql+psycopg://colacci_demo:local-demo-only-password@db:5432/colacci_test -e PYTHONPATH=/workspace colacci-law-api:latest python scripts/evaluate_fixtures.py

test-e2e:
	./scripts/test_e2e.sh

smoke:
	$(COMPOSE) run --rm api python scripts/smoke.py

audit:
	$(PY_RUN) pip-audit --require-hashes -r requirements.lock
	$(WEB_RUN) npm audit --audit-level=high

secret-scan:
	$(PY_RUN) python scripts/secret_scan.py

logs:
	$(COMPOSE) logs --no-color api worker
