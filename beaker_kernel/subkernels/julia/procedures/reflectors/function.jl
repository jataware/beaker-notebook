{# target_type: __function__ #}
{# function_name: _beaker_reflect_function #}
function _beaker_reflect_function(_name::String, _value)
    _qualname = string(_value)
    _tag = "function(`$(_qualname)`)"
    return Dict("tag" => _tag)
end
