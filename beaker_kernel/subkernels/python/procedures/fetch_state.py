{# Renders the Python fetch_state code that produces a canonical            -#}
{# KernelStatePayload (local_names + variables). Composed from the           -#}
{# reflectors registered on the subkernel.                                   -#}
import inspect as _inspect
import json as _json

class _BeakerStateEncoder(_json.JSONEncoder):
    def default(self, o):
        try:
            return super().default(o)
        except Exception:
            return str(o)

_EXCLUDED_LOCAL_NAMES = {{ excluded_local_names | tojson }}

{% for reflector in reflectors -%}
# reflector: {{ reflector.name }} (target_types={{ reflector.target_types | join(', ') }})
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

_result = {"local_names": {}, "variables": {}}
for _name, _value in dict(locals()).items():
    if _name.startswith("_"):
        continue
    if _name in _EXCLUDED_LOCAL_NAMES:
        continue
    try:
        _contribution = _beaker_dispatch_reflector(_name, _value)
    except Exception as _err:
        _contribution = {"tag": f"<reflector error: {type(_err).__name__}>"}
    _result["local_names"][_name] = _contribution.get("tag", "<unknown>")
    _description = _contribution.get("description")
    if _description is not None:
        _result["variables"][_name] = _description

_result = _json.loads(_json.dumps(_result, cls=_BeakerStateEncoder))
_result
