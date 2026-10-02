.DEFAULT_GOAL := help
SHELL := /bin/sh

API_BASE_URL ?= http://localhost:8000
TEST_DATABASE_URL ?= postgresql+asyncpg://rag:rag@localhost:55432/rag_test

.PHONY: help install dev up down logs migrate revision lint format typecheck test test-unit eval seed smoke clean

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Create the virtualenv and install all dependencies
	uv sync

dev: ## Run the API locally with autoreload (expects a reachable Postgres)
	uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

up: ## Start Postgres + API in Docker (migrations run on container start)
	docker compose up --build

down: ## Stop the stack and remove the database volume
	docker compose down -v

logs: ## Tail the API logs
	docker compose logs -f api

migrate: ## Apply migrations to DATABASE_URL
	uv run alembic upgrade head

revision: ## Autogenerate a migration: make revision m="add thing"
	uv run alembic revision --autogenerate -m "$(m)"

lint: ## Ruff lint + format check
	uv run ruff check .
	uv run ruff format --check .

format: ## Apply Ruff formatting and autofixes
	uv run ruff check --fix .
	uv run ruff format .

typecheck: ## mypy (strict)
	uv run mypy app evals scripts

test: ## Full test suite (integration tests need Postgres; see TEST_DATABASE_URL)
	TEST_DATABASE_URL=$(TEST_DATABASE_URL) uv run pytest -q

test-unit: ## Unit tests only (no database required)
	uv run pytest -q tests/unit

eval: ## Run the retrieval + refusal evaluation and write a report
	API_BASE_URL=$(API_BASE_URL) uv run python -m evals.run_eval

seed: ## Ingest sample_docs/ through the running API
	API_BASE_URL=$(API_BASE_URL) uv run python -m scripts.seed

smoke: ## End-to-end check: answerable, unanswerable, follow-up and SSE (run after seed)
	API_BASE_URL=$(API_BASE_URL) uv run python -m scripts.smoke

clean: ## Remove caches
	rm -rf .pytest_cache .ruff_cache .mypy_cache
