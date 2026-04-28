{# target_type: builtins.str, builtins.bytes #}
{# function_name: _beaker_reflect_string #}
def _beaker_reflect_string(_name, _value):
    _type_name = type(_value).__name__
    _length = len(_value)
    _tag = f"{_type_name}[{_length}]"
    _sample = repr(_value)
    if len(_sample) > 200:
        _sample = _sample[:200]
        _truncated = True
    else:
        _truncated = False
    return {
        "tag": _tag,
        "description": {
            "type": _type_name,
            "size": _length,
            "sample": _sample,
            "truncated": _truncated,
        },
    }
