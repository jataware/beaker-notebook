{# target_type: AbstractArray #}
{# function_name: _beaker_reflect_array #}
function _beaker_reflect_array(_name::String, _value::AbstractArray)
    _shape = join(string.(size(_value)), "x")
    _eltype = string(eltype(_value))
    _tag = "Array[$(_shape), $(_eltype)]"
    _sample = try
        _str = repr(_value)
        length(_str) > 300 ? (_str[1:300], true) : (_str, false)
    catch
        ("<unrepresentable>", false)
    end
    return Dict(
        "tag" => _tag,
        "description" => Dict(
            "type" => string(typeof(_value)),
            "shape" => _shape,
            "size" => length(_value),
            "summary" => Dict("eltype" => _eltype),
            "sample" => _sample[1],
            "truncated" => _sample[2],
        ),
    )
end
