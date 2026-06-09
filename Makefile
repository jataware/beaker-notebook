SHELL=/usr/bin/env bash
BASEDIR = $(shell pwd)

UI_OUTPUT_DIR=src/beaker_notebook/app/ui

# Determine which build command to use
PYTHON_BUILD_CMD = $(shell python3 -c "import build" >/dev/null 2>/dev/null && echo "python3 -m build")
UV_CMD = $(shell which uv >/dev/null 2>/dev/null && echo "uv build")
BUILD_CMD = $(or $(UV_CMD),$(PYTHON_BUILD_CMD))


define npm_build_deps
	$(shell find $(1)/src/ -name '*.ts' -or -name '*.vue') \
	$(1)/package*.json \
	$(1)/tsconfig*.json \
	$(wildcard $(1)/vite.config*.ts $(1)/vite.config*.json) 
endef

.PHONY:init
init:
	$(MAKE) .env 

.PHONY:build
build:
	@test "$(BUILD_CMD)" || { \
		echo "Missing build library. Install 'uv' or 'build' (E.g. 'pip install uv' or 'pip install build')"; \
		exit 1; \
	}
	$(MAKE) src/beaker_notebook/app/ui/index.html
	$(MAKE) beaker-vue/dist
	$(BUILD_CMD) .

.PHONY:clean
clean:
	rm -r dist */dist */html build */build ${UI_OUTPUT_DIR} || true

.PHONY:full-clean
full-clean:
	rm -r dist */dist */html build */build ${UI_OUTPUT_DIR} node_modules */node_modules || true

.PHONY:docs-up
docs-up:
	(cd docs && docker compose up -d) && \
	(sleep 1; python -m webbrowser "http://localhost:4000/")

.PHONY:docs-down
docs-down:
	(cd docs && docker compose down)

.PHONY:dev
dev:src/beaker_notebook/app/ui/index.html docker-build
	export BUILDX_BAKE_ENTITLEMENTS_FS=0; \
	cd docker && docker buildx bake dev
	VARIANT="dev" $(MAKE) docker-compose-up; \
	(sleep 1; python -m webbrowser "http://localhost:8888/"); \
	docker compose logs -f beaker || true; \

.env:
	@if [[ ! -e ./.env ]]; then \
		cp env.example .env; \
	fi \
	# echo "Don't forget to set your OPENAI key in the .env file!"; \

node_modules/:
	npm i && touch node_modules

beaker-ui/html:$(call npm_build_deps,beaker-ui) node_modules/
	npm run build && touch beaker-ui/html

src/beaker_notebook/app/ui/index.html:beaker-ui/html
	rsync -r --exclude="*.map" beaker-ui/html/* src/beaker_notebook/app/ui/

.PHONY:docker-build
docker-build:
	export BUILDX_BAKE_ENTITLEMENTS_FS=0; \
	cd docker && docker buildx bake

.PHONY:docker-compose-up
docker-compose-up:
	docker compose up -d

.PHONY:docker-compose-down
docker-compose-down:
	docker compose down
