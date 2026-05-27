{# target_type: numeric, integer, character, logical, complex #}
{# function_name: ._beaker_reflect_vector #}
._beaker_reflect_vector <- function(.name, .value) {
    .type_name <- class(.value)[1]
    .length <- length(.value)
    .tag <- paste0(.type_name, "[", .length, "]")
    .sample <- tryCatch({
        .head <- utils::head(.value, 5)
        .out <- paste(deparse(.head), collapse = "")
        if (nchar(.out) > 200) {
            list(substr(.out, 1, 200), TRUE)
        } else {
            list(.out, .length > 5)
        }
    }, error = function(e) list("<unrepresentable>", FALSE))
    list(
        tag = .tag,
        description = list(
            type = .type_name,
            size = .length,
            sample = .sample[[1]],
            truncated = .sample[[2]]
        )
    )
}
