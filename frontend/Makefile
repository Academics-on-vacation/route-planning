.PHONY: install run build test format format-check check docker-build clean

install:
	npm ci

run:
	npm run dev

build:
	npm run build

test:
	npm test

format:
	npm run format

format-check:
	npm run format:check

check: format-check test build

docker-build:
	docker build -t route-planning-frontend:local .

clean:
	rm -rf dist coverage .vite
