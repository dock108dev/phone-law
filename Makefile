SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE := docker compose
PY_RUN := $(COMPOSE) run --rm --no-deps api
WEB_RUN := $(COMPOSE) run --rm --no-deps web

.PHONY: help bootstrap dev stop clean lint typecheck test test-integration smoke audit secret-scan logs

help:
	@echo "Stable commands: bootstrap dev lint typecheck test test-integration smoke"

bootstrap:
	./scripts/bootstrap.sh

dev:
	./scripts/dev.sh

stop:
	$(COMPOSE) down

clean:
	./scripts/clean-local.sh

lint:
	$(PY_RUN) ruff format --check apps packages scripts tests
	$(PY_RUN) ruff check apps packages scripts tests
	$(PY_RUN) bandit -q -c pyproject.toml -r apps packages scripts
	$(PY_RUN) python scripts/verify_dependency_pins.py
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

smoke:
	$(COMPOSE) run --rm api python scripts/smoke.py

audit:
	$(PY_RUN) pip-audit --require-hashes -r requirements.lock
	$(WEB_RUN) npm audit --audit-level=high

secret-scan:
	$(PY_RUN) python scripts/secret_scan.py

logs:
	$(COMPOSE) logs --no-color api worker
