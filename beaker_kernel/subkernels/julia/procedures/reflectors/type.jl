{# target_type: __type__ #}
{# function_name: _beaker_reflect_type #}
function _beaker_reflect_type(_name::String, _value)
    _qualname = string(_value)
    _tag = _name == _qualname ? "type(`$(_qualname)`)" : "type(`$(_qualname)` as `$(_name)`)"
    return Dict("tag" => _tag)
end
