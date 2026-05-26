{# target_type: __default__ #}
{# function_name: _beaker_reflect_default #}
{# priority: 0 #}
def _beaker_reflect_default(_name, _value):
    _type = type(_value)
    _type_name = _type.__name__
    _full_type = f"{_type.__module__}.{_type.__qualname__}"
    _size = None
    if hasattr(_value, "__len__"):
        try:
            _size = len(_value)
        except Exception:
            _size = None
    _tag = _type_name if _size is None else f"{_type_name}[{_size}]"
    try:
        _sample = repr(_value)
    except Exception:
        _sample = f"<unrepresentable {_type_name}>"
    if len(_sample) > 400:
        _sample = _sample[:400]
        _truncated = True
    else:
        _truncated = False
    return {
        "tag": _tag,
        "description": {
            "type": _full_type,
            "size": _size,
            "sample": _sample,
            "truncated": _truncated,
        },
    }
