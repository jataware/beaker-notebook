{# target_type: AbstractDict #}
{# function_name: _beaker_reflect_dict #}
function _beaker_reflect_dict(_name::String, _value::AbstractDict)
    _length = length(_value)
    _tag = "Dict[$(_length)]"
    _key_kinds = Dict{String, Int}()
    _val_kinds = Dict{String, Int}()
    for (_k, _v) in collect(_value)[1:min(50, _length)]
        _kn = string(typeof(_k))
        _vn = string(typeof(_v))
        _key_kinds[_kn] = get(_key_kinds, _kn, 0) + 1
        _val_kinds[_vn] = get(_val_kinds, _vn, 0) + 1
    end
    _sample_keys = collect(keys(_value))[1:min(5, _length)]
    _sample = try
        _str = string(_sample_keys)
        length(_str) > 200 ? (_str[1:200], true) : (_str, _length > 5)
    catch
        ("<unrepresentable>", false)
    end
    return Dict(
        "tag" => _tag,
        "description" => Dict(
            "type" => string(typeof(_value)),
            "size" => _length,
            "summary" => Dict(
                "key_types" => _key_kinds,
                "value_types" => _val_kinds,
            ),
            "sample" => _sample[1],
            "truncated" => _sample[2],
        ),
    )
end
