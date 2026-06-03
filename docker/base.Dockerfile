ARG base_img=python:3.13

FROM ${base_img} AS base

LABEL "beaker"="true"

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt update -y && \
    apt install -y curl git vim-tiny unzip less net-tools
RUN ln -sf /usr/bin/vim.tiny /usr/bin/vim

RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=cache,target=/root/.cache/uv \
    pip install uv

COPY --from=assets entry-point.sh /usr/local/bin/entry-point.sh

ENTRYPOINT ["entry-point.sh"]
