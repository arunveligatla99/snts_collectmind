.PHONY: up down wait-ready clean clean-weights migrations test test-unit test-contract test-integration load-smoke load-full soak eval lint typecheck coverage demo demo-install demo-test demo-build demo-record demo-deploy

COMPOSE_FILE ?= infra/compose/docker-compose.yaml
COMPOSE := docker compose -f $(COMPOSE_FILE)
SLM_PROFILE ?= cpu

up:
	$(COMPOSE) --profile $(SLM_PROFILE) up -d

down:
	$(COMPOSE) down

clean:
	$(COMPOSE) down -v

clean-weights:
	rm -rf models/weights models/gguf

wait-ready:
	@bash scripts/wait_ready.sh

migrations:
	$(COMPOSE) exec -T postgres-timescale psql -U collectmind -d collectmind -f - < scripts/run_migrations.sql

test: test-unit test-contract test-integration

test-unit:
	pytest tests/unit -q

test-contract:
	pytest tests/contract -q

test-integration:
	pytest tests/integration -q

load-smoke:
	locust -f tests/load/locustfile_smoke.py --headless -u 10 -r 5 -t 60s

load-full:
	@echo "load-full is workflow_dispatch only; see .github/workflows/ci-workflow-dispatch.yaml"

soak:
	@echo "soak is nightly only; see .github/workflows/nightly.yaml"

eval:
	pytest tests/contract/test_slm_client_contract.py -q

lint:
	ruff check .
	ruff format --check .

typecheck:
	mypy src/

coverage:
	pytest --cov=src/collectmind --cov-report=term --cov-report=html

# ------- demo UI -----------------------------------------------------------

demo-install:
	cd demo && npm install --no-audit --no-fund

demo: demo-install
	cd demo && npm run dev

demo-build: demo-install
	cd demo && npm run gen:types && npm run build

demo-test: demo-install
	cd demo && npm run test

demo-record:
	bash demo/scripts/record_fixtures.sh

demo-deploy: demo-build
	cd demo && npx vercel --prod
