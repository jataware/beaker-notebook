{# Renders Julia code that produces a canonical KernelStatePayload. -#}
{# Composed from registered reflectors via a series of isa-checks.  -#}
using JSON3
using DisplayAs

_excluded_local_names = Set([{{ excluded_local_names | map('tojson') | join(', ') }}])

{% for reflector in reflectors -%}
# reflector: {{ reflector.name }} (target_types={{ reflector.target_types | join(', ') }})
{% include "reflectors/" ~ reflector.name ~ ".jl" %}

{% endfor %}

function _beaker_dispatch_reflector(_name::String, _value)
{% for reflector in reflectors %}
{% for target in reflector.target_types %}
{% if target == "__module__" %}
    if isa(_value, Module)
        return {{ reflector.function_name }}(_name, _value)
    end
{% elif target == "__function__" %}
    if isa(_value, Function)
        return {{ reflector.function_name }}(_name, _value)
    end
{% elif target == "__type__" %}
    if isa(_value, Type)
        return {{ reflector.function_name }}(_name, _value)
    end
{% elif target == "__default__" %}
    # default handled below
{% else %}
    try
        if isa(_value, {{ target }})
            return {{ reflector.function_name }}(_name, _value)
        end
    catch
    end
{% endif %}
{% endfor %}
{% endfor %}
{% for reflector in reflectors %}{% if "__default__" in reflector.target_types %}    return {{ reflector.function_name }}(_name, _value)
{% endif %}{% endfor %}
end

_module_syms = filter(k -> !startswith(string(k), "_") && !(string(k) in _excluded_local_names), names(@__MODULE__; imported=true))

_local_names = Dict{String, String}()
_variables = Dict{String, Any}()

for _sym in _module_syms
    _name = string(_sym)
    _value = try
        getfield(@__MODULE__, _sym)
    catch
        continue
    end
    _contribution = try
        _beaker_dispatch_reflector(_name, _value)
    catch err
        Dict("tag" => "<reflector error: $(typeof(err))>")
    end
    _local_names[_name] = get(_contribution, "tag", "<unknown>")
    if haskey(_contribution, "description")
        _variables[_name] = _contribution["description"]
    end
end

JSON3.write(Dict(
    "local_names" => _local_names,
    "variables" => _variables,
)) |> DisplayAs.unlimited
