import ast
from typing import Any, ClassVar

from ...lib.subkernel import CheckpointableBeakerSubkernel, Checkpoint

import logging
logger = logging.getLogger(__name__)


class PythonSubkernel(CheckpointableBeakerSubkernel):
    """
    Beaker subkernel for the python3 (IPython) ipykernel.

    See the following links for more information:
    https://ipykernel.readthedocs.io/en/stable/
    https://github.com/ipython/ipykernel
    """
    DISPLAY_NAME = "Python 3"
    SLUG = "python3"
    JUPYTER_LANGUAGE = "python"
    KERNEL_NAME = "python3"

    WEIGHT = 20

    SERIALIZATION_EXTENSION = "pickle"

    EXCLUDED_LOCAL_NAMES: ClassVar[frozenset[str]] = frozenset({
        "In", "Out", "get_ipython", "exit", "quit", "open",
    })

    @classmethod
    def parse_subkernel_return(cls, execution_result) -> Any:
        return_str = execution_result.get("return")
        if return_str:
            python_obj = ast.literal_eval(return_str)
            return python_obj

    async def generate_checkpoint_from_state(self) -> Checkpoint:
        save_state_code = """
import inspect as _inspect
import json as _json
import dill as _dill
class _SubkernelStateEncoder(_json.JSONEncoder):
    def default(self, o):
        # if callable(o):
            # return f"Function named"
            # return super().default(o)
        try:
            return super().default(o)
        except:
            return str(o)

_result = {}
for _name, _value in dict(locals()).items():
    if _name.startswith('_') or _name in ('In', 'Out', 'get_ipython', 'exit', 'quit', 'open'):
        continue
    _path = f"%s/{_name}.pkl"
    with open(_path, "wb") as _f:
        try:
            _dill.dump(_value, _f)
        except Exception as e:
            continue
        _result[_name] = _path

_result = _json.loads(_json.dumps(_result, cls=_SubkernelStateEncoder))
del _inspect, _json, _dill
_result
""" % self.storage_prefix
        response = await self.context.evaluate(save_state_code)
        return response["return"]


    async def load_checkpoint(self, checkpoint: Checkpoint):
        vars = await self.context.evaluate("""
import dill as _dill
_exclusion_critieria = lambda name: name.startswith('_') or name in ('In', 'Out', 'get_ipython', 'exit', 'quit', 'open')
[ name for name, value in dict(locals()).items() if not _exclusion_critieria(name) ]
""")
        await self.context.execute(f"del {', '.join(vars['return'])}")
        deserialization_code = ""
        for varname, filename in checkpoint.items():
            deserialization_code += f"""

with open("{filename}", "rb") as _file:
    {varname} = _dill.load(_file)

"""
        deserialization_code += "del _dill"
        await self.context.execute(deserialization_code)

    async def setup(self):
        setup_code = f"""
import importlib
import os
import site
import sys
if site.USER_SITE not in sys.path:
    os.makedirs(site.USER_SITE, exist_ok=True)
    sys.path.append(site.USER_SITE)
    importlib.invalidate_caches()
del importlib, os, site, sys
"""
        await self.context.execute(setup_code)

    def format_kernel_state(self, state):
        """Format a canonical KernelStatePayload (local_names + variables) into
        the UI-friendly tree the front-end renders. Bins the flat local_names
        map back into modules/classes/functions/variables for human display.
        """
        formatted_state: dict[str, dict[str, Any]] = {
            "modules": {},
            "variables": {},
            "functions": {},
            "classes": {},
        }

        local_names = state.get("local_names", {}) or {}
        variables = state.get("variables", {}) or {}

        for name, tag in local_names.items():
            if tag.startswith("module("):
                formatted_state["modules"][name] = {"label": f"{name}: {tag}"}
            elif tag.startswith("class("):
                formatted_state["classes"][name] = {"label": f"{name}: {tag}"}
            elif tag.startswith("function("):
                formatted_state["functions"][name] = {"label": f"{name}: {tag}"}
            else:
                # Data variable; richer entry comes from `variables` below.
                # Stash the tag for now in case there's no detailed entry.
                formatted_state["variables"][name] = {"label": f"{name}: {tag}"}

        for name, details in variables.items():
            type_name = details.get("type", "?")
            size = details.get("size")
            shape = details.get("shape")
            shape_suffix = ""
            if shape:
                shape_suffix = f"[{shape}]"
            elif size is not None:
                shape_suffix = f"[{size}]"
            label = f"{name} ({type_name}{shape_suffix})"

            children: list[dict[str, Any]] = []
            sample = details.get("sample")
            if sample:
                children.append({"label": sample})
            summary = details.get("summary")
            if summary:
                children.append({"label": f"summary: {summary}"})

            entry: dict[str, Any] = {"label": label}
            if children:
                entry["children"] = children
            formatted_state["variables"][name] = entry

        return formatted_state

    def get_treesitter_language(self):
        try:
            from tree_sitter import Language
            from tree_sitter_python import language
            return Language(language())
        except ImportError as err:
            logger.warning(f"Couldn't import treesitter library: {err}")
            return None
