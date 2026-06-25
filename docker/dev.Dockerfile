FROM beaker-notebook

USER root

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt update && apt install -y gosu
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system debugpy hupper

RUN mkdir -p /usr/local/bin/pre-exec
RUN mkdir -p /root/.local/lib/python3.13/site-packages
COPY --from=assets install-local-packages.sh /usr/local/bin/pre-exec/
COPY --from=assets hupper_debug.py /usr/local/lib/python3.13/site-packages/

RUN echo "beaker-notebook" > /opt/package_list

ENV RUN_USER=beaker

ENV CMD="hupper -m hupper_debug --"
