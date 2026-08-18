SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE := docker compose
PY_RUN := $(COMPOSE) run --rm --no-deps api
WEB_RUN := $(COMPOSE) run --rm --no-deps web

.PHONY: help bootstrap seed-demo dev stop clean generate-test-audio test-audio test-transcription-contract transcription-live-preflight test-transcription-live lint typecheck test test-integration test-fixtures test-e2e smoke audit secret-scan logs

help:
	@echo "Stable commands: bootstrap generate-test-audio test-audio test-transcription-contract transcription-live-preflight test-transcription-live seed-demo dev lint typecheck test test-integration test-fixtures test-e2e smoke"

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
	PYTHONPATH=. python3 scripts/generate_test_audio.py

test-audio: generate-test-audio
	$(COMPOSE) run --rm --no-deps --user root -v /tmp/colacci-law-slice3a:/tmp/colacci-law-slice3a api python scripts/test_audio_boundary.py

test-transcription-contract: generate-test-audio
	$(COMPOSE) run --rm --no-deps --user root -v /tmp/colacci-law-slice3a:/tmp/colacci-law-slice3a api python scripts/test_transcription_contract.py

transcription-live-preflight:
	PYTHONPATH=. COLACCI_SYNTHETIC_ROOT=/tmp/colacci-law-slice3b python3 scripts/generate_test_audio.py
	docker run --rm --network none -v "$(CURDIR):/workspace:ro" -v /tmp/colacci-law-slice3b:/tmp/colacci-law-slice3b -w /workspace -e PYTHONPATH=/workspace -e APP_PROFILE=live_test -e ALLOW_REAL_CALL_DATA=false -e REAL_CALL_PROCESSING_AUTHORIZED=false -e LIVE_TRANSCRIPTION_ENABLED=true -e LIVE_TRANSCRIPTION_AUTHORIZED=true -e TRANSCRIPTION_APPROVAL_REFERENCE=OWNER-CHAT-2026-08-17-SLICE-3B -e TRANSCRIPTION_MODEL_ID=gpt-4o-transcribe-diarize -e TRANSCRIPTION_MAX_REQUESTS=4 -e TRANSCRIPTION_MAX_TOTAL_AUDIO_SECONDS=120 -e TRANSCRIPTION_MAX_TOTAL_BYTES=20971520 -e TRANSCRIPTION_TEST_BUDGET_USD=1.00 -e CALL_SOURCE_ADAPTER=generated_synthetic -e TRANSCRIBER_ADAPTER=openai_live -e ANALYZER_ADAPTER=disabled -e NOTIFICATION_ADAPTER=noop -e OBJECT_STORAGE_BACKEND=local_synthetic -e MEDIA_TEMP_ROOT=/tmp/colacci-law-slice3b/objects -e OPENAI_BASE_URL="$${OPENAI_BASE_URL:-https://api.openai.com/v1}" -e OPENAI_API_KEY -e OPENAI_PROJECT_ID -e OPENAI_PROJECT_DATA_CONTROLS_APPROVED colacci-law-api:latest python scripts/transcription_live_preflight.py

test-transcription-live:
	docker run --rm -v "$(CURDIR):/workspace:ro" -v /tmp/colacci-law-slice3b:/tmp/colacci-law-slice3b -w /workspace -e PYTHONPATH=/workspace -e APP_PROFILE=live_test -e ALLOW_REAL_CALL_DATA=false -e REAL_CALL_PROCESSING_AUTHORIZED=false -e LIVE_TRANSCRIPTION_ENABLED=true -e LIVE_TRANSCRIPTION_AUTHORIZED=true -e TRANSCRIPTION_APPROVAL_REFERENCE=OWNER-CHAT-2026-08-17-SLICE-3B -e TRANSCRIPTION_MODEL_ID=gpt-4o-transcribe-diarize -e TRANSCRIPTION_MAX_REQUESTS=4 -e TRANSCRIPTION_MAX_TOTAL_AUDIO_SECONDS=120 -e TRANSCRIPTION_MAX_TOTAL_BYTES=20971520 -e TRANSCRIPTION_TEST_BUDGET_USD=1.00 -e TRANSCRIPTION_LIVE_EXECUTION_CONFIRMED -e CALL_SOURCE_ADAPTER=generated_synthetic -e TRANSCRIBER_ADAPTER=openai_live -e ANALYZER_ADAPTER=disabled -e NOTIFICATION_ADAPTER=noop -e OBJECT_STORAGE_BACKEND=local_synthetic -e MEDIA_TEMP_ROOT=/tmp/colacci-law-slice3b/objects -e OPENAI_BASE_URL="$${OPENAI_BASE_URL:-https://api.openai.com/v1}" -e OPENAI_API_KEY -e OPENAI_PROJECT_ID -e OPENAI_PROJECT_DATA_CONTROLS_APPROVED colacci-law-api:latest python scripts/test_transcription_live.py

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
