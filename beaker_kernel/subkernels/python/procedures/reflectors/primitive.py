{# target_type: builtins.int, builtins.float, builtins.bool, builtins.complex, builtins.NoneType #}
{# function_name: _beaker_reflect_primitive #}
def _beaker_reflect_primitive(_name, _value):
    _type_name = type(_value).__name__
    _sample = repr(_value)
    if len(_sample) > 80:
        _sample = _sample[:80]
        _truncated = True
    else:
        _truncated = False
    if _truncated:
        _tag = _type_name
    else:
        _tag = f"{_type_name}({_sample})"
    return {
        "tag": _tag,
        "description": {
            "type": _type_name,
            "sample": _sample,
            "truncated": _truncated,
        },
    }
