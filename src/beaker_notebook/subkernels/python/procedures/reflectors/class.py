{# target_type: __class__ #}
{# function_name: _beaker_reflect_class #}
def _beaker_reflect_class(_name, _value):
    _module = getattr(_value, "__module__", "")
    _qualname = getattr(_value, "__qualname__", _value.__name__)
    if _module and _module != "builtins":
        _full = f"{_module}.{_qualname}"
    else:
        _full = _qualname
    if _name == _qualname:
        _tag = f"class(`{_full}`)"
    else:
        _tag = f"class(`{_full}` as `{_name}`)"
    return {"tag": _tag}
