{# target_type: pandas.core.frame.DataFrame #}
{# function_name: _beaker_reflect_dataframe #}
def _beaker_reflect_dataframe(_name, _value):
    _rows, _cols = _value.shape
    _shape = f"{_rows}x{_cols}"
    _tag = f"DataFrame[{_shape}]"

    _dtypes = {str(_col): str(_dt) for _col, _dt in _value.dtypes.items()}
    try:
        _sample = _value.head(3).to_string()
    except Exception:
        _sample = "<unrepresentable>"
    if len(_sample) > 400:
        _sample = _sample[:400]
        _truncated = True
    else:
        _truncated = _rows > 3
    return {
        "tag": _tag,
        "description": {
            "type": "pandas.DataFrame",
            "shape": _shape,
            "size": int(_rows),
            "summary": {"columns": _dtypes},
            "sample": _sample,
            "truncated": _truncated,
        },
    }
