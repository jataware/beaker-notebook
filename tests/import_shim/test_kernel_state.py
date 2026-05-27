"""
Tests for beaker_kernel.lib.kernel_state.

Covers:
- apply_sample_budget: under, exact, over, multi-variable spillover, zero
- render_agent_payload: empty, names-only, full, with extension keys
"""

import json

from beaker_kernel.lib.kernel_state import (
    apply_sample_budget,
    render_agent_payload,
)


# -- apply_sample_budget --


def _payload(samples: dict[str, int]) -> dict:
    """Helper: build a payload where each variable's sample is `n`-char-long."""
    return {
        "local_names": {name: f"type[{n}]" for name, n in samples.items()},
        "variables": {
            name: {
                "type": "str",
                "sample": "x" * n,
                "truncated": False,
            }
            for name, n in samples.items()
        },
    }


def test_apply_sample_budget_under_budget_keeps_all_samples():
    payload = _payload({"a": 50, "b": 50})
    result = apply_sample_budget(payload, budget=300)
    assert len(result["variables"]["a"]["sample"]) == 50
    assert len(result["variables"]["b"]["sample"]) == 50
    assert result["variables"]["a"]["truncated"] is False
    assert result["variables"]["b"]["truncated"] is False


def test_apply_sample_budget_exact_budget_keeps_all_samples():
    payload = _payload({"a": 100, "b": 200})
    result = apply_sample_budget(payload, budget=300)
    assert len(result["variables"]["a"]["sample"]) == 100
    assert len(result["variables"]["b"]["sample"]) == 200
    assert result["variables"]["a"]["truncated"] is False
    assert result["variables"]["b"]["truncated"] is False


def test_apply_sample_budget_over_budget_truncates_overrunner():
    payload = _payload({"a": 200, "b": 200})
    result = apply_sample_budget(payload, budget=300)
    # a fits (200 <= 300), b only has 100 chars left, gets truncated to 100
    assert len(result["variables"]["a"]["sample"]) == 200
    assert result["variables"]["a"]["truncated"] is False
    assert len(result["variables"]["b"]["sample"]) == 100
    assert result["variables"]["b"]["truncated"] is True


def test_apply_sample_budget_subsequent_variables_get_stripped():
    payload = _payload({"a": 300, "b": 100, "c": 100})
    result = apply_sample_budget(payload, budget=300)
    assert len(result["variables"]["a"]["sample"]) == 300
    # b and c are both stripped because the budget was exhausted by a
    assert result["variables"]["b"]["sample"] is None
    assert result["variables"]["b"]["truncated"] is True
    assert result["variables"]["c"]["sample"] is None
    assert result["variables"]["c"]["truncated"] is True


def test_apply_sample_budget_zero_strips_all_samples():
    payload = _payload({"a": 50, "b": 50})
    result = apply_sample_budget(payload, budget=0)
    assert result["variables"]["a"]["sample"] is None
    assert result["variables"]["b"]["sample"] is None
    assert result["variables"]["a"]["truncated"] is True
    assert result["variables"]["b"]["truncated"] is True


def test_apply_sample_budget_skips_variables_without_sample():
    payload = {
        "local_names": {"a": "type"},
        "variables": {
            "a": {"type": "module", "truncated": False},  # no sample key
        },
    }
    result = apply_sample_budget(payload, budget=100)
    assert "sample" not in result["variables"]["a"] or result["variables"]["a"].get("sample") is None
    # Variable without a sample shouldn't get its truncated flag flipped.
    assert result["variables"]["a"]["truncated"] is False


def test_apply_sample_budget_handles_empty_variables():
    payload = {"local_names": {"a": "type"}, "variables": {}}
    result = apply_sample_budget(payload, budget=100)
    assert result["variables"] == {}


# -- render_agent_payload --


def test_render_empty_payload_returns_just_heading():
    result = render_agent_payload({})
    assert result.strip() == "## Kernel state"


def test_render_local_names_only():
    payload = {
        "local_names": {
            "pd": "module(`pandas`)",
            "df": "DataFrame[5x2]",
        },
    }
    result = render_agent_payload(payload)
    assert "## Kernel state" in result
    assert "### Names in scope" in result
    assert "- `pd`: module(`pandas`)" in result
    assert "- `df`: DataFrame[5x2]" in result
    assert "### Variables" not in result


def test_render_variables_only():
    payload = {
        "variables": {
            "df": {"type": "pandas.DataFrame", "shape": "5x2"},
        },
    }
    result = render_agent_payload(payload)
    assert "### Names in scope" not in result
    assert "### Variables" in result
    assert "pandas.DataFrame" in result
    assert "```application/json" in result


def test_render_full_payload():
    payload = {
        "local_names": {"x": "int(42)"},
        "variables": {"x": {"type": "int", "sample": "42", "truncated": False}},
    }
    result = render_agent_payload(payload)
    assert "### Names in scope" in result
    assert "- `x`: int(42)" in result
    assert "### Variables" in result
    # Confirm the JSON block parses
    json_block = result.split("```application/json\n", 1)[1].split("\n```", 1)[0]
    parsed = json.loads(json_block)
    assert parsed == payload["variables"]


def test_render_passes_through_extension_keys():
    payload = {
        "local_names": {"a": "type"},
        "variables": {},
        "lean_specific_thing": {"foo": "bar"},
    }
    result = render_agent_payload(payload)
    assert "### Additional state" in result
    assert "lean_specific_thing" in result


def test_render_serializes_unjsonifiable_via_default_str():
    class NotJsonable:
        def __repr__(self):
            return "NotJsonable()"

    payload = {
        "variables": {"thing": {"type": "x", "sample": NotJsonable()}},
    }
    # Should not raise; default=str fallback handles it.
    result = render_agent_payload(payload)
    assert "NotJsonable()" in result
