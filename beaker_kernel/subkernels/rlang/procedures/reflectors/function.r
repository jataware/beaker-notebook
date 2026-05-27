{# target_type: __function__ #}
{# function_name: ._beaker_reflect_function #}
._beaker_reflect_function <- function(.name, .value) {
    .args <- tryCatch(
        paste(deparse(args(.value)), collapse = ""),
        error = function(e) "(...)"
    )
    .args <- sub("^function ", "", .args)
    .args <- sub(" NULL$", "", .args)
    list(tag = paste0("function(`", .name, .args, "`)"))
}
