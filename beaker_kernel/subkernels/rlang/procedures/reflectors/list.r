{# target_type: list #}
{# function_name: ._beaker_reflect_list #}
._beaker_reflect_list <- function(.name, .value) {
    .length <- length(.value)
    .tag <- paste0("list[", .length, "]")
    .names <- names(.value)
    .sample <- if (is.null(.names)) {
        paste0("[unnamed list of ", .length, " items]")
    } else {
        .head_names <- utils::head(.names, 5)
        paste0("names: ", paste(.head_names, collapse = ", "))
    }
    .truncated <- .length > 5
    list(
        tag = .tag,
        description = list(
            type = "list",
            size = .length,
            sample = .sample,
            truncated = .truncated
        )
    )
}
