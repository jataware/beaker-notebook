{# target_type: data.frame #}
{# function_name: ._beaker_reflect_data_frame #}
._beaker_reflect_data_frame <- function(.name, .value) {
    .rows <- nrow(.value)
    .cols <- ncol(.value)
    .shape <- paste0(.rows, "x", .cols)
    .col_classes <- sapply(.value, function(c) class(c)[1])
    .sample <- tryCatch({
        .out <- capture.output(print(utils::head(.value, 3)))
        .joined <- paste(.out, collapse = "\n")
        if (nchar(.joined) > 400) {
            list(substr(.joined, 1, 400), TRUE)
        } else {
            list(.joined, .rows > 3)
        }
    }, error = function(e) list("<unrepresentable>", FALSE))
    list(
        tag = paste0("data.frame[", .shape, "]"),
        description = list(
            type = "data.frame",
            shape = .shape,
            size = .rows,
            summary = list(columns = as.list(.col_classes)),
            sample = .sample[[1]],
            truncated = .sample[[2]]
        )
    )
}
