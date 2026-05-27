{# target_type: __default__ #}
{# function_name: ._beaker_reflect_default #}
{# priority: 0 #}
._beaker_reflect_default <- function(.name, .value) {
    .type_name <- class(.value)[1]
    .sample <- tryCatch({
        .out <- capture.output(print(.value))
        .joined <- paste(.out, collapse = "\n")
        if (nchar(.joined) > 200) {
            list(substr(.joined, 1, 200), TRUE)
        } else {
            list(.joined, FALSE)
        }
    }, error = function(e) list("<unrepresentable>", FALSE))
    list(
        tag = .type_name,
        description = list(
            type = .type_name,
            sample = .sample[[1]],
            truncated = .sample[[2]]
        )
    )
}
