{# target_type: __callable__ #}
{# function_name: _beaker_reflect_function #}
def _beaker_reflect_function(_name, _value):
    try:
        _sig = str(_inspect.signature(_value))
    except (TypeError, ValueError):
        _sig = "(...)"
    _module = getattr(_value, "__module__", "") or ""
    _qualname = getattr(_value, "__qualname__", getattr(_value, "__name__", _name))
    if _module and _module != "builtins" and _module != "__main__":
        _full = f"{_module}.{_qualname}"
    else:
        _full = _qualname
    if _name == _qualname:
        _tag = f"function(`{_full}{_sig}`)"
    else:
        _tag = f"function(`{_full}{_sig}` as `{_name}`)"
    return {"tag": _tag}
