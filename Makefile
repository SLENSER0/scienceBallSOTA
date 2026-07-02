.DEFAULT_GOAL := help
UV ?= uv
PY := $(UV) run

.PHONY: help bootstrap up down dev lint fmt type test test-cov check clean \
        fe-install fe-lint fe-build fe-test vendor ingest seed demo api agent frontend \
        pre-commit

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

bootstrap: ## Install all Python (uv) + frontend (pnpm) deps
	$(UV) sync --all-packages
	-cd apps/frontend && pnpm install --frozen-lockfile || cd apps/frontend && pnpm install

up: ## Start server-profile stack (docker compose)
	docker compose -f infra/docker-compose.yml up -d

down: ## Stop server-profile stack
	docker compose -f infra/docker-compose.yml down

dev: ## Run API + frontend in parallel (embedded profile)
	$(MAKE) -j2 api frontend

api: ## Run the API gateway (:8000)
	$(PY) uvicorn api_gateway.main:app --host 0.0.0.0 --port 8000 --reload

agent: ## Run the agent service (:8010)
	$(PY) uvicorn agent_service.main:app --host 0.0.0.0 --port 8010 --reload

frontend: ## Run the Vite frontend (:3000)
	cd apps/frontend && pnpm dev

lint: ## Ruff lint
	$(PY) ruff check .

fmt: ## Ruff format
	$(PY) ruff format .

type: ## Mypy type-check
	$(PY) mypy apps packages

test: ## Run pytest
	$(PY) pytest -q

test-cov: ## Run pytest with coverage
	$(PY) pytest --cov --cov-report=term-missing

check: lint ## Reproduce CI locally (lint + format-check + test)
	$(PY) ruff format --check .
	$(PY) pytest -q

fe-install: ## Install frontend deps
	cd apps/frontend && pnpm install

fe-lint: ## Frontend lint
	cd apps/frontend && pnpm lint

fe-build: ## Frontend production build
	cd apps/frontend && pnpm build

fe-test: ## Frontend tests
	cd apps/frontend && pnpm test

vendor: ## Clone OSS reference repos into third_party/ (study only)
	bash scripts/vendor.sh

ingest: ## Ingest the data corpus into the embedded KG (limit via N=)
	$(PY) python -m ingestion_service.cli ingest --limit $(or $(N),20)

index: ## Build vector+keyword search indexes from the graph
	$(PY) python -m ingestion_service.cli index

seed: ## Seed the demo graph (idempotent)
	$(PY) python infra/neo4j/seed/seed_graph.py

demo: ## Run the 4 acceptance queries end-to-end
	$(PY) python -m kg_eval.runner --suite domain_science_ball

pre-commit: ## Run all pre-commit hooks
	$(PY) pre-commit run --all-files

clean: ## Remove caches and embedded stores
	rm -rf .ruff_cache .mypy_cache .pytest_cache .coverage htmlcov
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
