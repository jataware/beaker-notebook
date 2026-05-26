import ast
import json
import logging
from typing import Any, ClassVar

from ...lib.subkernel import BeakerSubkernel

logger = logging.getLogger(__name__)


class JuliaSubkernel(BeakerSubkernel):
    """
    Beaker subkernel for the Julia language, using the IJulia kernel from the IJulia.jl package.

    More information at:
    https://julialang.github.io/IJulia.jl/stable/
    https://github.com/JuliaLang/IJulia.jl
    """
    DISPLAY_NAME = "Julia"
    SLUG = "julia"
    JUPYTER_LANGUAGE = "julia"

    WEIGHT = 30

    EXCLUDED_LOCAL_NAMES: ClassVar[frozenset[str]] = frozenset({
        "Base", "Core", "IJulia", "In", "Main", "Out", "ans",
        "clear_history", "eval", "include",
    })

    @classmethod
    def parse_subkernel_return(cls, execution_result) -> Any:
        return_raw = execution_result.get("return")
        if return_raw:
            return_str = ast.literal_eval(return_raw)
            try:
                python_obj = json.loads(return_str)
            except json.JSONDecodeError:
                raise
            return python_obj
