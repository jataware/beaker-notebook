# syntax=docker/dockerfile:1-labs
ARG BASE_VERSION=base
ARG package=beaker-notebook

FROM ${BASE_VERSION} AS ui_build

RUN curl -fsSL https://deb.nodesource.com/setup_24.x | bash -
RUN apt update -y && apt install -y rsync make nodejs
COPY --parents --from=src ./Makefile ./beaker-vue ./beaker-ts ./beaker-ui ./package*.json /build/beaker-ui/
WORKDIR /build/beaker-ui
RUN mkdir -p src/beaker_notebook/app/ui
RUN make src/beaker_notebook/app/ui/index.html


FROM ${BASE_VERSION}
ARG package

COPY --parents --from=src ./pyproject.toml ./README.md ./Makefile ./src /build/${package}/
RUN --mount=type=cache,target=/root/.cache/pip --mount=type=cache,target=/root/.cache/uv uv pip install --system -r /build/${package}/pyproject.toml
WORKDIR /build/${package}

# Copy ui build artifacts from ui_build stage
COPY --from=ui_build /build/beaker-ui/src/beaker_notebook/app/ui /build/${package}/src/beaker_notebook/app/ui


# Cleanup
RUN (cd /build/${package} && rm -fr ./dist ./**/dist ./**/build || true)
# Build package, outputing to /dist
RUN --mount=type=cache,target=/root/.cache/pip --mount=type=cache,target=/root/.cache/uv uv build --wheel --out-dir /dist --no-build-isolation .
