{# target_type: __module__ #}
{# function_name: _beaker_reflect_module #}
def _beaker_reflect_module(_name, _value):
    _full = getattr(_value, "__name__", None) or _name
    if _name == _full:
        _tag = f"module(`{_full}`)"
    else:
        _tag = f"module(`{_full}` as `{_name}`)"
    return {"tag": _tag}
