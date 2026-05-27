"""
Tests for the reflector registry and discovery in beaker_notebook.lib.reflector.

Covers:
- Header parsing (single block, multi-line block, multiple blocks, missing keys)
- target_type comma-list normalization
- ReflectorRegistry add/dedupe/iteration/dispatch ordering
- ReflectorRegistry.from_jinja_env (filtering, header parsing, priority)
"""

import textwrap

import pytest
from jinja2 import DictLoader, Environment

from beaker_notebook.lib.reflector import (
    DEFAULT_PRIORITY,
    REFLECTOR_SUBDIR,
    Reflector,
    ReflectorRegistry,
    parse_reflector_header,
)


# -- Header parsing --


def test_parse_header_single_block():
    src = textwrap.dedent("""
        {# target_type: pandas.DataFrame #}
        {# function_name: _beaker_reflect_dataframe #}
        def _beaker_reflect_dataframe(_n, _v):
            return {}
    """)
    header = parse_reflector_header(src)
    assert header["target_type"] == "pandas.DataFrame"
    assert header["function_name"] == "_beaker_reflect_dataframe"


def test_parse_header_multi_line_block():
    src = textwrap.dedent("""
        {#
        target_type: numpy.ndarray
        function_name: _beaker_reflect_ndarray
        priority: 150
        #}
        def _beaker_reflect_ndarray(_n, _v):
            return {}
    """)
    header = parse_reflector_header(src)
    assert header["target_type"] == "numpy.ndarray"
    assert header["function_name"] == "_beaker_reflect_ndarray"
    assert header["priority"] == "150"


def test_parse_header_stops_at_first_non_comment():
    src = textwrap.dedent("""
        {# target_type: foo.Bar #}
        # this is a python comment, not a Jinja header
        {# this_should_not_appear: yes #}
        def fn(): pass
    """)
    header = parse_reflector_header(src)
    assert header == {"target_type": "foo.Bar"}


def test_parse_header_ignores_lines_without_colon():
    src = textwrap.dedent("""
        {#
        target_type: foo.Bar
        no colon line
        function_name: _fn
        #}
    """)
    header = parse_reflector_header(src)
    assert header == {"target_type": "foo.Bar", "function_name": "_fn"}


def test_parse_header_empty_when_no_jinja_comment():
    src = "def f(): pass\n"
    assert parse_reflector_header(src) == {}


# -- Registry behavior --


def _make_reflector(name, target_types=("foo.Bar",), function_name=None, priority=DEFAULT_PRIORITY):
    if function_name is None:
        function_name = f"_reflect_{name}"
    if isinstance(target_types, str):
        target_types = (target_types,)
    return Reflector(
        name=name,
        target_types=tuple(target_types),
        function_name=function_name,
        template=None,  # not used in these tests
        priority=priority,
        metadata={},
    )


def test_registry_empty():
    reg = ReflectorRegistry()
    assert len(reg) == 0
    assert not reg
    assert list(reg) == []


def test_registry_add_and_lookup():
    reg = ReflectorRegistry()
    r = _make_reflector("dataframe")
    reg.add(r)
    assert reg["dataframe"] is r
    assert "dataframe" in reg
    assert len(reg) == 1
    assert bool(reg)


def test_registry_first_add_wins_on_duplicate_name():
    reg = ReflectorRegistry()
    first = _make_reflector("dataframe", function_name="_first")
    second = _make_reflector("dataframe", function_name="_second")
    reg.add(first)
    reg.add(second)
    assert reg["dataframe"] is first


def test_registry_iteration_order_is_insertion_order():
    reg = ReflectorRegistry()
    for name in ["zeta", "alpha", "middle"]:
        reg.add(_make_reflector(name))
    assert list(reg) == ["zeta", "alpha", "middle"]


def test_registry_in_dispatch_order_sorts_by_priority_then_name():
    reg = ReflectorRegistry()
    reg.add(_make_reflector("default", priority=0))
    reg.add(_make_reflector("dataframe", priority=200))
    reg.add(_make_reflector("ndarray", priority=200))
    reg.add(_make_reflector("primitive", priority=100))
    ordered = [r.name for r in reg.in_dispatch_order()]
    # priority desc, then name asc within ties
    assert ordered == ["dataframe", "ndarray", "primitive", "default"]


def test_registry_by_target_type_includes_each_target():
    reg = ReflectorRegistry()
    reg.add(_make_reflector("primitive", target_types=("builtins.int", "builtins.float")))
    reg.add(_make_reflector("default", target_types=("__default__",)))
    by_target = reg.by_target_type
    assert by_target["builtins.int"].name == "primitive"
    assert by_target["builtins.float"].name == "primitive"
    assert by_target["__default__"].name == "default"


def test_registry_by_target_type_first_registration_wins_on_collision():
    reg = ReflectorRegistry()
    reg.add(_make_reflector("a", target_types=("shared",), function_name="_a"))
    reg.add(_make_reflector("b", target_types=("shared",), function_name="_b"))
    assert reg.by_target_type["shared"].name == "a"


# -- from_jinja_env discovery --


def _env_with(files: dict[str, str]) -> Environment:
    return Environment(loader=DictLoader(files))


def test_from_jinja_env_loads_well_formed_reflectors():
    env = _env_with({
        "reflectors/dataframe.py": textwrap.dedent("""\
            {# target_type: pandas.DataFrame #}
            {# function_name: _beaker_reflect_dataframe #}
            def _beaker_reflect_dataframe(_n, _v):
                return {}
        """),
        "reflectors/default.py": textwrap.dedent("""\
            {# target_type: __default__ #}
            {# function_name: _beaker_reflect_default #}
            {# priority: 0 #}
            def _beaker_reflect_default(_n, _v):
                return {}
        """),
    })
    reg = ReflectorRegistry.from_jinja_env(env)
    assert set(reg.keys()) == {"dataframe", "default"}
    assert reg["dataframe"].priority == DEFAULT_PRIORITY
    assert reg["default"].priority == 0
    assert reg["dataframe"].function_name == "_beaker_reflect_dataframe"


def test_from_jinja_env_supports_comma_list_target_type():
    env = _env_with({
        "reflectors/primitive.py": textwrap.dedent("""\
            {# target_type: builtins.int, builtins.float, builtins.bool #}
            {# function_name: _beaker_reflect_primitive #}
            def _beaker_reflect_primitive(_n, _v):
                return {}
        """),
    })
    reg = ReflectorRegistry.from_jinja_env(env)
    assert reg["primitive"].target_types == (
        "builtins.int", "builtins.float", "builtins.bool",
    )


def test_from_jinja_env_skips_files_without_required_headers(caplog):
    env = _env_with({
        "reflectors/incomplete.py": textwrap.dedent("""\
            {# target_type: foo.Bar #}
            def _fn(_n, _v):
                return {}
        """),
    })
    reg = ReflectorRegistry.from_jinja_env(env)
    assert "incomplete" not in reg
    assert any("missing required header keys" in rec.message for rec in caplog.records)


def test_from_jinja_env_skips_dotfiles_and_dunders():
    env = _env_with({
        "reflectors/.gitkeep": "",
        "reflectors/__pycache__.py": "{# target_type: x #}\n{# function_name: y #}\n",
        "reflectors/good.py": textwrap.dedent("""\
            {# target_type: foo.Bar #}
            {# function_name: _fn #}
            def _fn(_n, _v): return {}
        """),
    })
    reg = ReflectorRegistry.from_jinja_env(env)
    assert set(reg.keys()) == {"good"}


def test_from_jinja_env_ignores_files_outside_reflectors_subdir():
    env = _env_with({
        "fetch_state.py": "irrelevant",
        "reflectors/x.py": textwrap.dedent("""\
            {# target_type: foo.Bar #}
            {# function_name: _fn #}
        """),
    })
    reg = ReflectorRegistry.from_jinja_env(env)
    assert set(reg.keys()) == {"x"}


def test_from_jinja_env_falls_back_to_default_priority_on_bad_value(caplog):
    env = _env_with({
        "reflectors/bad_priority.py": textwrap.dedent("""\
            {# target_type: foo.Bar #}
            {# function_name: _fn #}
            {# priority: not-an-int #}
        """),
    })
    reg = ReflectorRegistry.from_jinja_env(env)
    assert reg["bad_priority"].priority == DEFAULT_PRIORITY
    assert any("non-integer priority" in rec.message for rec in caplog.records)


def test_reflector_subdir_constant():
    # Sanity: the subdir constant is the documented name and the loader uses it.
    assert REFLECTOR_SUBDIR == "reflectors"
