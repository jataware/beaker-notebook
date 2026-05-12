SHELL=/usr/bin/env bash
BASEDIR = $(shell pwd)

# Determine which build command to use
PYTHON_BUILD_CMD = $(shell python3 -c "import build" >/dev/null 2>/dev/null && echo "python3 -m build")
UV_CMD = $(shell which uv >/dev/null 2>/dev/null && echo "uv build")
BUILD_CMD = $(or $(UV_CMD),$(PYTHON_BUILD_CMD))


define npm_build_deps
	$(shell find $(1)/src/ -name '*.ts' -or -name '*.vue') \
	$(1)/package*.json \
	$(1)/tsconfig*.json \
	$(wildcard $(1)/vite.config*.ts $(1)/vite.config*.json) \
	$(1)/node_modules
endef

.PHONY:init
init:
	make .env beaker-ui/node_modules

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
	rm -r beaker-ts/dist beaker-vue/dist beaker-ui/html build dist src/beaker_notebook/app/ui || true


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

beaker-ts/node_modules:beaker-ts/package*.json
	(cd beaker-ts/ && npm install --include=dev && npm link) && \
	touch beaker-ts/node_modules

beaker-ts/dist:$(call npm_build_deps,beaker-ts)
	(cd beaker-ts/ && npm run build) && \
	touch beaker-ts/dist

beaker-vue/node_modules:beaker-vue/package*.json beaker-ts/dist
	(cd beaker-vue && npm install --include=dev) && \
	echo touch beaker-vue/node_modules

beaker-vue/dist:$(call npm_build_deps,beaker-vue)
	(cd beaker-vue && npm run build) && \
	touch beaker-vue/dist

beaker-ui/node_modules:beaker-ui/package*.json beaker-ts/dist beaker-vue/dist
	(cd beaker-ui && npm install --include=dev) && \
	touch beaker-ui/node_modules

beaker-ui/html:$(call npm_build_deps,beaker-ui) beaker-vue/dist
	(cd beaker-ui && npm run build) && \
	touch beaker-ui/html

src/beaker_notebook/app/ui/index.html:beaker-ui/node_modules beaker-ui/html
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
