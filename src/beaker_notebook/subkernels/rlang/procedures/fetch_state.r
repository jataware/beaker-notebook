{# Renders R code that produces a canonical KernelStatePayload. -#}
if (!requireNamespace("jsonlite", quietly = TRUE)) {
    install.packages("jsonlite", repos = "https://cloud.r-project.org")
}
suppressPackageStartupMessages(library(jsonlite))

._excluded_local_names <- c({{ excluded_local_names | map('tojson') | join(', ') }})

{% for reflector in reflectors -%}
# reflector: {{ reflector.name }} (target_types={{ reflector.target_types | join(', ') }})
{% include "reflectors/" ~ reflector.name ~ ".r" %}

{% endfor %}

._beaker_dispatch_reflector <- function(.name, .value) {
{% for reflector in reflectors %}
{% for target in reflector.target_types %}
{% if target == "__function__" %}
    if (is.function(.value)) {
        return({{ reflector.function_name }}(.name, .value))
    }
{% elif target == "__default__" %}
    # default handled below
{% else %}
    if (inherits(.value, {{ target | tojson }})) {
        return({{ reflector.function_name }}(.name, .value))
    }
{% endif %}
{% endfor %}
{% endfor %}
{% for reflector in reflectors %}{% if "__default__" in reflector.target_types %}    return({{ reflector.function_name }}(.name, .value))
{% endif %}{% endfor %}
}

._all_names <- ls(envir = globalenv())
._local_names <- list()
._variables <- list()

for (._n in ._all_names) {
    if (startsWith(._n, ".")) next
    if (._n %in% ._excluded_local_names) next
    ._v <- tryCatch(get(._n, envir = globalenv()), error = function(e) NULL)
    if (is.null(._v)) next
    ._contribution <- tryCatch(
        ._beaker_dispatch_reflector(._n, ._v),
        error = function(e) list(tag = paste0("<reflector error: ", conditionMessage(e), ">"))
    )
    ._local_names[[._n]] <- if (is.null(._contribution$tag)) "<unknown>" else ._contribution$tag
    if (!is.null(._contribution$description)) {
        ._variables[[._n]] <- ._contribution$description
    }
}

._result <- list(local_names = ._local_names, variables = ._variables)
cat(jsonlite::toJSON(._result, auto_unbox = TRUE, null = "null"))
