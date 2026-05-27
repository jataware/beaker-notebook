"""
Tests for the `beaker subkernel verify` CLI command.

These tests exercise the verify command via Click's CliRunner against a fake
subkernel rooted in a temp directory. Each test sets up a procedures/ tree,
points a fixture subkernel at it via procedure_location, and asserts that
verify reports the expected pass/fail outcome.
"""

import os
import textwrap
from pathlib import Path

import pytest
from click.testing import CliRunner

from beaker_kernel.lib.subkernel import BeakerSubkernel


@pytest.fixture
def fake_subkernel_factory(tmp_path, monkeypatch):
    """Build a fake subkernel registered into the autodiscovery path.

    Returns a callable that takes (slug, procedures_layout) where
    procedures_layout is a dict of relative-path -> file-content. A subkernel
    class is dynamically created with procedure_location pointed at the
    temp dir, and the autodiscovery is monkeypatched to surface it.
    """
    def _factory(slug: str, layout: dict[str, str]):
        proc_root = tmp_path / slug / "procedures"
        proc_root.mkdir(parents=True, exist_ok=True)
        for relpath, content in layout.items():
            target = proc_root / relpath
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)

        @classmethod
        def _abstract_parse(cls, execution_result):
            return None

        cls = type(
            f"Fake{slug.capitalize()}Subkernel",
            (BeakerSubkernel,),
            {
                "DISPLAY_NAME": f"Fake {slug}",
                "SLUG": slug,
                "JUPYTER_LANGUAGE": "fake",
                "procedure_location": str(proc_root),
                "parse_subkernel_return": _abstract_parse,
                "__abstractmethods__": frozenset(),
            },
        )

        # Inject this fake into autodiscover_subkernels' returned mapping.
        from beaker_kernel.lib import subkernel as subkernel_mod

        original = subkernel_mod.autodiscover_subkernels

        def patched_autodiscover():
            result = dict(original())
            result[slug] = cls
            return result

        monkeypatch.setattr(
            subkernel_mod, "autodiscover_subkernels", patched_autodiscover
        )
        # The CLI imports `from beaker_kernel.lib.subkernel import autodiscover_subkernels`
        # at function-call time, so the monkeypatch on the module attr is sufficient.
        return cls, proc_root

    return _factory


def _run_verify(slug: str | None = None) -> tuple[int, str]:
    from beaker_kernel.cli.subkernel import verify_subkernel

    runner = CliRunner()
    args = [slug] if slug else []
    result = runner.invoke(verify_subkernel, args, catch_exceptions=False)
    return result.exit_code, result.output


# -- Happy path --


VALID_FETCH_STATE = "# pretend fetch_state body\n"
VALID_DESCRIBE_VARIABLES = "# pretend describe_variables body\n"

VALID_DEFAULT_REFLECTOR = textwrap.dedent("""\
    {# target_type: __default__ #}
    {# function_name: _reflect_default #}
    def _reflect_default(_n, _v):
        return {}
""")

VALID_DATAFRAME_REFLECTOR = textwrap.dedent("""\
    {# target_type: pandas.DataFrame #}
    {# function_name: _reflect_dataframe #}
    {# priority: 200 #}
    def _reflect_dataframe(_n, _v):
        return {}
""")


def test_verify_passes_on_well_formed_subkernel(fake_subkernel_factory):
    fake_subkernel_factory("happypath", {
        "fetch_state.py": VALID_FETCH_STATE,
        "describe_variables.py": VALID_DESCRIBE_VARIABLES,
        "reflectors/default.py": VALID_DEFAULT_REFLECTOR,
        "reflectors/dataframe.py": VALID_DATAFRAME_REFLECTOR,
    })
    code, output = _run_verify("happypath")
    assert code == 0, output
    assert "RESULT: happypath OK" in output
    assert "[ok]   fetch_state procedure" in output
    assert "[ok]   describe_variables procedure" in output


# -- Failure cases --


def test_verify_fails_when_fetch_state_missing(fake_subkernel_factory):
    fake_subkernel_factory("nofetch", {
        "reflectors/default.py": VALID_DEFAULT_REFLECTOR,
    })
    code, output = _run_verify("nofetch")
    assert code != 0
    assert "No fetch_state.<ext> procedure found" in output
    assert "RESULT: nofetch FAILED" in output


def test_verify_warns_but_passes_when_describe_variables_missing(fake_subkernel_factory):
    fake_subkernel_factory("nodescribe", {
        "fetch_state.py": VALID_FETCH_STATE,
        "reflectors/default.py": VALID_DEFAULT_REFLECTOR,
    })
    code, output = _run_verify("nodescribe")
    # describe_variables is a warn, not a fail
    assert code == 0, output
    assert "[warn] No describe_variables" in output
    assert "RESULT: nodescribe OK" in output


def test_verify_fails_on_reflector_missing_required_header(fake_subkernel_factory):
    fake_subkernel_factory("badheader", {
        "fetch_state.py": VALID_FETCH_STATE,
        "reflectors/incomplete.py": textwrap.dedent("""\
            {# target_type: foo.Bar #}
            def _reflect_incomplete(_n, _v):
                return {}
        """),
    })
    code, output = _run_verify("badheader")
    assert code != 0
    assert "missing required header keys" in output
    assert "RESULT: badheader FAILED" in output


def test_verify_fails_on_function_name_not_in_body(fake_subkernel_factory):
    fake_subkernel_factory("mismatch", {
        "fetch_state.py": VALID_FETCH_STATE,
        "reflectors/wrong.py": textwrap.dedent("""\
            {# target_type: foo.Bar #}
            {# function_name: _reflect_declared #}
            def _reflect_actual(_n, _v):
                return {}
        """),
    })
    code, output = _run_verify("mismatch")
    assert code != 0
    assert "_reflect_declared" in output
    assert "not present anywhere in template body" in output


def test_verify_fails_on_target_type_collision(fake_subkernel_factory):
    fake_subkernel_factory("collision", {
        "fetch_state.py": VALID_FETCH_STATE,
        "reflectors/a.py": textwrap.dedent("""\
            {# target_type: shared.Type #}
            {# function_name: _reflect_a #}
            def _reflect_a(_n, _v):
                return {}
        """),
        "reflectors/b.py": textwrap.dedent("""\
            {# target_type: shared.Type #}
            {# function_name: _reflect_b #}
            def _reflect_b(_n, _v):
                return {}
        """),
    })
    code, output = _run_verify("collision")
    assert code != 0
    assert "already declared by" in output
    assert "shared.Type" in output


def test_verify_fails_on_jinja_parse_error(fake_subkernel_factory):
    fake_subkernel_factory("badjinja", {
        "fetch_state.py": "{% if unclosed_block %}\n# missing endif\n",
        "reflectors/default.py": VALID_DEFAULT_REFLECTOR,
    })
    code, output = _run_verify("badjinja")
    assert code != 0
    assert "parse error" in output


def test_verify_unknown_slug_raises_click_exception():
    code, output = _run_verify("nonexistent-slug-xyz")
    assert code != 0
    assert "No subkernel registered" in output


def test_verify_skips_dotfiles_in_reflectors_dir(fake_subkernel_factory):
    fake_subkernel_factory("dotfiles", {
        "fetch_state.py": VALID_FETCH_STATE,
        "reflectors/.gitkeep": "",
        "reflectors/default.py": VALID_DEFAULT_REFLECTOR,
    })
    code, output = _run_verify("dotfiles")
    assert code == 0, output
    # .gitkeep should not appear as a checked reflector
    assert ".gitkeep" not in output
