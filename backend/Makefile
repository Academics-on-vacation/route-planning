.PHONY: install sync run test lint format format-check check docker-build clean

install: sync

sync:
	uv sync --group dev

run:
	uv run --env-file ../.env uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test:
	uv run pytest

lint:
	uv run ruff check .

format:
	uv run ruff check --fix-only .
	uv run ruff format .

format-check:
	uv run ruff format --check .

check: lint format-check test

docker-build:
	docker build -t route-planning-backend:local .

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage
