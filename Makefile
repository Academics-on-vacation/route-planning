COMPOSE ?= docker compose

.PHONY: install up down restart logs ps build migrate check compose-check backend-test lint format format-check install-hooks clean

install:
	$(MAKE) -C backend install
	$(MAKE) -C frontend install

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) restart

logs:
	$(COMPOSE) logs -f

ps:
	$(COMPOSE) ps

build:
	$(COMPOSE) build

migrate:
	$(COMPOSE) run --rm --build migrate

backend-test:
	$(MAKE) -C backend test

check:
	$(MAKE) -C backend check
	$(MAKE) -C frontend check
	$(MAKE) compose-check

compose-check:
	$(COMPOSE) config --quiet

lint:
	$(MAKE) -C backend lint

format:
	$(MAKE) -C backend format
	$(MAKE) -C frontend format

format-check:
	$(MAKE) -C backend format-check
	$(MAKE) -C frontend format-check

install-hooks:
	uv run --project backend pre-commit install

clean:
	$(COMPOSE) down -v
