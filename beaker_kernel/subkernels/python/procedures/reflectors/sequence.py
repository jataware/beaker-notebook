{# target_type: builtins.list, builtins.tuple, builtins.set, builtins.frozenset #}
{# function_name: _beaker_reflect_sequence #}
def _beaker_reflect_sequence(_name, _value):
    _type_name = type(_value).__name__
    _length = len(_value)
    _tag = f"{_type_name}[{_length}]"

    _kinds = {}
    _items = list(_value) if not isinstance(_value, (set, frozenset)) else list(_value)
    for _item in _items[:50]:
        _kinds[type(_item).__name__] = _kinds.get(type(_item).__name__, 0) + 1

    _head = _items[:5]
    try:
        _sample = repr(_head)
    except Exception:
        _sample = "<unrepresentable>"
    if len(_sample) > 300:
        _sample = _sample[:300]
        _truncated = True
    else:
        _truncated = _length > 5
    return {
        "tag": _tag,
        "description": {
            "type": _type_name,
            "size": _length,
            "summary": {"element_types": _kinds},
            "sample": _sample,
            "truncated": _truncated,
        },
    }
