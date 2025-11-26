SHELL=/usr/bin/env bash
BASEDIR = $(shell pwd)

.PHONY:init
init:
	make .env beaker-vue/node_modules

.PHONY:build
build:
	rm -r beaker-ts/dist/* beaker-vue/dist/* beaker-vue/html/* beaker_kernel/service/ui/* || true
	make beaker_kernel/service/ui/index.html
	hatch build

.PHONY:clean
clean:
	rm -r beaker-ts/dist/* beaker-vue/dist/* beaker-vue/html/* build/* dist/* beaker_kernel/service/ui/* || true


.PHONY:docs-up
docs-up:
	(cd docs && docker compose up -d) && \
	(sleep 1; python -m webbrowser "http://localhost:4000/")

.PHONY:docs-down
docs-down:
	(cd docs && docker compose down)

.PHONY:dev
dev:beaker_kernel/service/ui/index.html
	docker compose up -d --build && \
	(sleep 1; python -m webbrowser "http://localhost:8888/"); \
	docker compose logs -f jupyter || true; \

.env:
	@if [[ ! -e ./.env ]]; then \
		cp env.example .env; \
		echo "Don't forget to set your OPENAI key in the .env file!"; \
	fi

beaker-vue/node_modules:beaker-vue/package*.json
	(cd beaker-ts/ && npm install --include=dev && npm run build) && \
	(cd beaker-vue && npm install --include=dev) && \
	touch beaker-vue/node_modules

beaker_kernel/service/ui/index.html:beaker-vue/node_modules beaker-vue/**
	(cd beaker-ts/ && npm install && npm run build) && \
	(cd beaker-vue/ && npm install && npm run build) && \
	rsync -r --exclude="*.map" beaker-vue/html/* beaker_kernel/service/ui/
	#rm -r beaker_kernel/service/ui/* || true; \

.PHONY:changed-files
changed-files:
	find dev_ui/ \( -name "build" -prune \) -o -cnewer dev_ui/build/index.js \( -name '*.js' -or -name '*.ts' \) -ls
