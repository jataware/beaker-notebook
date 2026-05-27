{# target_type: pandas.core.series.Series #}
{# function_name: _beaker_reflect_series #}
def _beaker_reflect_series(_name, _value):
    _length = int(_value.shape[0])
    _dtype = str(_value.dtype)
    _tag = f"Series[{_length}, {_dtype}]"

    try:
        _sample = _value.head(5).to_string()
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
            "type": "pandas.Series",
            "size": _length,
            "summary": {"dtype": _dtype, "name": str(_value.name) if _value.name is not None else None},
            "sample": _sample,
            "truncated": _truncated,
        },
    }
