{# target_type: __module__ #}
{# function_name: _beaker_reflect_module #}
function _beaker_reflect_module(_name::String, _value::Module)
    _full = string(nameof(_value))
    _tag = _name == _full ? "module(`$(_full)`)" : "module(`$(_full)` as `$(_name)`)"
    return Dict("tag" => _tag)
end
