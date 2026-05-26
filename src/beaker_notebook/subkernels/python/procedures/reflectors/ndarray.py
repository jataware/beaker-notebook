{# target_type: numpy.ndarray #}
{# function_name: _beaker_reflect_ndarray #}
def _beaker_reflect_ndarray(_name, _value):
    _shape = "x".join(str(_d) for _d in _value.shape) or "0"
    _dtype = str(_value.dtype)
    _tag = f"ndarray[{_shape}, {_dtype}]"

    try:
        _sample = repr(_value)
    except Exception:
        _sample = "<unrepresentable>"
    if len(_sample) > 300:
        _sample = _sample[:300]
        _truncated = True
    else:
        _truncated = False
    return {
        "tag": _tag,
        "description": {
            "type": "numpy.ndarray",
            "shape": _shape,
            "size": int(_value.size),
            "summary": {"dtype": _dtype},
            "sample": _sample,
            "truncated": _truncated,
        },
    }
