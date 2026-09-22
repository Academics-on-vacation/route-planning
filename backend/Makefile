.PHONY: install sync run migrate test lint format format-check check docker-build clean

install: sync

sync:
	uv sync --locked --group dev

run:
	uv run --env-file ../.env uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

migrate:
	uv run --locked --env-file ../.env alembic upgrade head

test:
	uv run --locked pytest

lint:
	uv run --locked ruff check .

format:
	uv run --locked ruff check --fix-only .
	uv run --locked ruff format .

format-check:
	uv run --locked ruff format --check .

check: lint format-check test

docker-build:
	docker build -t route-planning-backend:local .

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage
