.PHONY: install run build format format-check check docker-build clean

install:
	npm ci

run:
	npm run dev

build:
	npm run build

format:
	npm run format

format-check:
	npm run format:check

check: format-check build

docker-build:
	docker build -t route-planning-frontend:local .

clean:
	rm -rf dist coverage .vite
