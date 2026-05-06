SHELL=/usr/bin/env bash
BASEDIR = $(shell pwd)

define npm_build_deps
	$(shell find $(1)/src/ -name '*.ts' -or -name '*.vue') \
	$(1)/package*.json \
	$(1)/tsconfig*.json \
	$(wildcard $(1)/vite.config*.ts $(1)/vite.config*.json) \
	$(1)/node_modules
endef

.PHONY:init
init:
	make .env beaker-vue/node_modules

.PHONY:build
build:
	$(MAKE) beaker_kernel/app/ui/index.html
	$(MAKE) beaker-vue/dist
	hatch build

.PHONY:clean
clean:
	rm -r beaker-ts/dist beaker-vue/dist beaker-vue/html build dist beaker_kernel/app/ui || true


.PHONY:docs-up
docs-up:
	(cd docs && docker compose up -d) && \
	(sleep 1; python -m webbrowser "http://localhost:4000/")

.PHONY:docs-down
docs-down:
	(cd docs && docker compose down)

.PHONY:dev
dev:beaker_kernel/app/ui/index.html
	docker compose up -d --build && \
	(sleep 1; python -m webbrowser "http://localhost:8888/"); \
	docker compose logs -f jupyter || true; \

.env:
	@if [[ ! -e ./.env ]]; then \
		cp env.example .env; \
		echo "Don't forget to set your OPENAI key in the .env file!"; \
	fi

beaker-ts/node_modules:beaker-ts/package*.json
	(cd beaker-ts/ && npm install --include=dev && npm link) && \
	touch beaker-ts/node_modules

beaker-ts/dist:$(call npm_build_deps,beaker-ts)
	(cd beaker-ts/ && npm run build) && \
	touch beaker-ts/dist

beaker-vue/node_modules:beaker-vue/package*.json beaker-ts/dist
	(cd beaker-vue && npm install --include=dev && npm link beaker-kernel) && \
	touch beaker-vue/node_modules

beaker-vue/node_modules/beaker-kernel:beaker-ts/dist
	(cd beaker-vue && npm link beaker-kernel)

beaker-vue/dist:$(call npm_build_deps,beaker-vue)
	(cd beaker-vue && npm run build-lib) && \
	touch beaker-vue/dist

beaker-vue/html:$(call npm_build_deps,beaker-vue)
	(cd beaker-vue && npm run build-ui) && \
	touch beaker-vue/html

beaker_kernel/app/ui/index.html:beaker-vue/node_modules beaker-vue/html
	rsync -r --exclude="*.map" beaker-vue/html/* beaker_kernel/app/ui/

