COMPOSE ?= docker compose

.PHONY: install up down restart logs ps build check compose-check backend-test format install-hooks clean

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

backend-test:
	$(MAKE) -C backend test

check:
	$(MAKE) -C backend check
	$(MAKE) -C frontend check
	$(MAKE) compose-check

compose-check:
	$(COMPOSE) config --quiet

format:
	$(MAKE) -C backend format
	$(MAKE) -C frontend format

install-hooks:
	uv run --project backend pre-commit install

clean:
	$(COMPOSE) down -v
