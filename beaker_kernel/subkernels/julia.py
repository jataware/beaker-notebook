import ast
import json
import logging
from typing import Any

from ..lib.subkernel import BeakerSubkernel

logger = logging.getLogger(__name__)


def get_kernel_name():
    from jupyter_client.kernelspec import KernelSpecManager
    ksm = KernelSpecManager()
    kernel_specs = ksm.get_all_specs()
    for kernel, specs in kernel_specs.items():
        if specs.get("spec", {}).get("language", None) == "julia":
            return kernel
    return None

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
    KERNEL_NAME = get_kernel_name()

# varinfo / filter / display
    FETCH_STATE_CODE = """
using JSON3
using DisplayAs

_var_syms = filter(k -> !(k in [:Base, :Core, :IJulia, :In, :Main, :Out, :ans, :clear_history, :eval, :include]), names(@__MODULE__; imported=true))
_functions = filter(k -> isa(getfield(@__MODULE__, k), Function), _var_syms)
_modules = filter(k -> isa(getfield(@__MODULE__, k), Module), _var_syms)
_variables = filter(k -> !(k in [_functions; _modules; :_functions; :_modules; :_variables; :_var_syms]), _var_syms)

JSON3.write(Dict(
  "functions" => _functions,
  "modules" => _modules,
  "variables" => _variables
)) |> DisplayAs.unlimited
"""

    WEIGHT = 30

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
