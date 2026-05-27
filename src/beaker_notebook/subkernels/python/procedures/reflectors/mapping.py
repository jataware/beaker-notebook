{# target_type: builtins.dict #}
{# function_name: _beaker_reflect_mapping #}
def _beaker_reflect_mapping(_name, _value):
    _type_name = type(_value).__name__
    _length = len(_value)
    _tag = f"{_type_name}[{_length}]"

    _key_kinds = {}
    _value_kinds = {}
    for _k, _v in list(_value.items())[:50]:
        _key_kinds[type(_k).__name__] = _key_kinds.get(type(_k).__name__, 0) + 1
        _value_kinds[type(_v).__name__] = _value_kinds.get(type(_v).__name__, 0) + 1

    _sample_keys = list(_value.keys())[:5]
    try:
        _sample = repr(_sample_keys)
    except Exception:
        _sample = "<unrepresentable keys>"
    if len(_sample) > 200:
        _sample = _sample[:200]
        _truncated = True
    else:
        _truncated = _length > 5
    return {
        "tag": _tag,
        "description": {
            "type": _type_name,
            "size": _length,
            "summary": {
                "key_types": _key_kinds,
                "value_types": _value_kinds,
            },
            "sample": _sample,
            "truncated": _truncated,
        },
    }
