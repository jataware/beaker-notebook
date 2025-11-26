import ast
from typing import Any

from ..lib.subkernel import CheckpointableBeakerSubkernel, Checkpoint

import logging
logger = logging.getLogger(__name__)

VARIABLE_MAX_SHORT_CONTENTS_DISPLAY = 10

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

    FETCH_STATE_CODE: str = """
import inspect as _inspect
import json as _json
import dill as _dill
import logging as _logging
_logger = _logging.getLogger(__name__)

class _SubkernelStateEncoder(_json.JSONEncoder):
    def default(self, o):
        # if callable(o):
            # return f"Function named"
            # return super().default(o)
        try:
            return super().default(o)
        except:
            return str(o)

_result = {
    "modules": {},
    "variables": {},
    "functions": {},
    "classes": {}
}
for _name, _value in dict(locals()).items():
    try:
        if _name.startswith('_') or _name in ('In', 'Out', 'get_ipython', 'exit', 'quit', 'open'):
            continue
        if callable(_value):
            if isinstance(_value, type):
                _result["classes"][_name] = {
                    'docstring': _inspect.getdoc(_value)
                }
            else:
                _fndetails = {
                    'docstring': _inspect.getdoc(_value),
                    'signature': str(_inspect.signature(_value))
                }
                _result["functions"][_name] = _fndetails
        elif _inspect.ismodule(_value):

            try:
                _path = str(_value.__file__)
            except AttributeError:
                _path = "(built in)"
            _result["modules"][_name] = {
                'path': _path,
                'full_name': str(_value.__name__)
            }
        else:
            import pandas as _pandas
            _size = ''
            if id(_value) in (id(globals()), id(locals)):
                _vardetails = {
                    'value': "{...skipped...}",
                    'type': str(type(_value)),
                    'size': '',
                }
            else:
                _size = ''
                if hasattr(_value, "shape"):
                    _size = _value.shape
                elif hasattr(_value, "__len__"):
                    try:
                        _size = len(_value)
                    except Exception:
                        pass

                # bounds check long sequences for size and things like Ellipsis not being serializable
                _safe_value = _value
                _truncated = False
                try:
                    _safe_value = _value.head()
                    _truncated = True
                except AttributeError:
                    pass
                try:
                    _safe_value = _value[:99]
                    if len(_value) > 99:
                        _truncated = True
                except Exception:
                    pass

                _vardetails = {
                    'value': _safe_value,
                    'type': type(_value).__name__,
                    'size': str(_size),
                    'truncated': _truncated
                }
            _result["variables"][_name] = _vardetails
    except Exception as e:
        _logger.warning(f"FETCH_STATE_CODE: failed to get variable details for variable `{_name}` of type `{type(_value)}`: {e}")
try:
    _result = _json.loads(_json.dumps(_result, cls=_SubkernelStateEncoder))
except Exception as e:
    _logger.warning(f"FETCH_STATE_CODE: failed to serialize state: {e}")
    _result = {}
_result
"""

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
        formatted_state = {
            "modules": {},
            "variables": {},
            "functions": {},
            "classes": {}
        }
        for module, details in state.get("modules", {}).items():
            aliased_name = f": {details['full_name']}" if module != details["full_name"] else ""
            label = f"{module}{aliased_name}"
            children = [{"label": f'import path: {details["path"]}'}]
            formatted_state["modules"][module] = {
                "label": label,
                "children": children
            }

        for variable, details in state.get("variables", {}).items():
            size_suffix = f"[{details['size']}]" if details["size"] != "" else ""
            label = f"{variable} ({details['type']}{size_suffix}): "

            contents = str(details["value"])
            if len(contents) > VARIABLE_MAX_SHORT_CONTENTS_DISPLAY:
                label += f"{contents[:VARIABLE_MAX_SHORT_CONTENTS_DISPLAY]}..."
            else:
                label += contents

            if details["truncated"]:
                dropdown_contents = f"(truncated)\n{contents}"
            else:
                dropdown_contents = contents

            formatted_state["variables"][variable] = {
                "label": label,
                "children": [{"label": dropdown_contents}]
            }

        for function, details in state.get("functions", {}).items():
            payload: dict[str, Any] = {
                "label": f"{function} {details['signature']}"
            }
            if details["docstring"] is not None:
                payload["children"] = [{"label": details["docstring"]}]
            formatted_state["functions"][function] = payload

        for state_class, details in state.get("classes", {}).items():
            payload = {
                "label": f"{state_class}"
            }
            if details["docstring"] is not None:
                payload["children"] = [{"label": details["docstring"]}]
            formatted_state["classes"][state_class] = payload

        return formatted_state

    def get_treesitter_language(self):
        try:
            from tree_sitter import Language
            from tree_sitter_python import language
            return Language(language())
        except ImportError as err:
            logger.warning(f"Couldn't import treesitter library: {err}")
            return None
