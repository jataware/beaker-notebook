ARG BASE_VERSION=base

# Way of allowing optional building (not currently functional)
ARG JULIA_ENABLED=false
ARG R_ENABLED=false

ARG JULIA_BASE=julia:latest

# Julia build stage to keep build size down
FROM julia:latest AS julia-latest
ENV JULIA_PATH=/usr/local/julia
ENV JULIA_DEPOT_PATH=/usr/local/julia/depot
RUN julia -e ' \
    packages = [ \
        "IJulia", "DataSets", "XLSX", "Plots", "Downloads", "DataFrames", "ImageShow", "FileIO", "JSON3", "CSV", "DisplayAs"  \
    ]; \
    using Pkg; \
    Pkg.add(packages); Pkg.precompile()' && \
    rm -rf /usr/local/julia/share/doc && \
    rm -rf /usr/local/julia/share/man && \
    rm -rf /root/.julia/logs && \
    rm -rf /root/.julia/registries && \
    julia -e 'using Pkg; Pkg.gc()'
ENV JULIA_DEPOT_PATH=":/usr/local/julia/depot"

# Julia build conditional
FROM julia-latest AS julia-enabled-true
FROM base AS julia-enabled-false
RUN mkdir -p /usr/local/julia
FROM julia-enabled-${JULIA_ENABLED} AS julia-build


# Main notebook build
FROM ${BASE_VERSION}
ARG R_ENABLED
ARG JULIA_ENABLED

ENV JULIA_PATH=/usr/local/julia
COPY --from=julia-build /usr/local/julia /usr/local/julia
ENV PATH="$JULIA_PATH/bin:$PATH"
ENV JULIA_DEPOT_PATH=":/usr/local/julia/depot"

# R install
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    if [ "$R_ENABLED" == "true" ]; then \
        apt update -y && \
        apt install -y --no-install-recommends r-base-core r-cran-irkernel; \
    fi

RUN --mount=type=bind,from=packages,source=/dist,target=/dist \
    for wheel in `ls -1 /dist/*.whl`; do \
        uv pip install --system $wheel && echo $wheel >> /opt/package_list; \
    done

RUN adduser --home /beaker beaker
USER beaker
WORKDIR /beaker

CMD ["-m", "beaker_notebook.app.notebook_app", "--ip", "0.0.0.0"]
