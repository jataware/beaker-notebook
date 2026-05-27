{# target_type: __default__ #}
{# function_name: _beaker_reflect_default #}
{# priority: 0 #}
function _beaker_reflect_default(_name::String, _value)
    _type_name = string(typeof(_value))
    _sample = try
        _str = repr(_value)
        length(_str) > 200 ? (_str[1:200], true) : (_str, false)
    catch
        ("<unrepresentable>", false)
    end
    return Dict(
        "tag" => _type_name,
        "description" => Dict(
            "type" => _type_name,
            "sample" => _sample[1],
            "truncated" => _sample[2],
        ),
    )
end
