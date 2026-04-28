{# Renders code that produces a richer description for the named variables. -#}
{# Reuses the same reflector dispatch as fetch_state but only emits entries -#}
{# for the requested names; sample-byte budget is applied post-fetch.       -#}
import inspect as _inspect
import json as _json

class _BeakerStateEncoder(_json.JSONEncoder):
    def default(self, o):
        try:
            return super().default(o)
        except Exception:
            return str(o)

_TARGET_NAMES = {{ target_names | tojson }}

{% for reflector in reflectors -%}
{% include "reflectors/" ~ reflector.name ~ ".py" %}

{% endfor %}

_REFLECTORS = {
{%- for reflector in reflectors %}
{%- for target in reflector.target_types %}
    {{ target | tojson }}: {{ reflector.function_name }},
{%- endfor %}
{%- endfor %}
}

def _beaker_dispatch_reflector(_name, _value):
    if _inspect.ismodule(_value):
        return _REFLECTORS["__module__"](_name, _value)
    if _inspect.isclass(_value):
        return _REFLECTORS["__class__"](_name, _value)
    if callable(_value):
        return _REFLECTORS["__callable__"](_name, _value)
    for _cls in type(_value).__mro__:
        _key = f"{_cls.__module__}.{_cls.__qualname__}"
        if _key in _REFLECTORS:
            return _REFLECTORS[_key](_name, _value)
    return _REFLECTORS["__default__"](_name, _value)

_result = {"variables": {}, "missing": []}
_locals_snapshot = dict(locals())
for _target in _TARGET_NAMES:
    if _target not in _locals_snapshot:
        _result["missing"].append(_target)
        continue
    _value = _locals_snapshot[_target]
    try:
        _contribution = _beaker_dispatch_reflector(_target, _value)
    except Exception as _err:
        _result["variables"][_target] = {
            "type": type(_value).__name__,
            "sample": f"<reflector error: {type(_err).__name__}: {_err}>",
            "truncated": False,
        }
        continue
    _description = _contribution.get("description")
    if _description is None:
        # Module/class/function: synthesize a minimal description from the tag
        _description = {
            "type": type(_value).__name__,
            "sample": _contribution.get("tag", ""),
            "truncated": False,
        }
    _result["variables"][_target] = _description

_result = _json.loads(_json.dumps(_result, cls=_BeakerStateEncoder))
_result
