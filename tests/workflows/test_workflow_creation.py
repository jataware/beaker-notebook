"""Tests for workflow construction/loading validation (lib/workflow.py).

Covers issue #196 item 3: a workflow whose stages contain duplicate names must
fail to load with a clear message rather than silently collapsing two stages
into one progress slot.

`WorkflowState.from_workflow` keys progress by stage name, and
`update_workflow_stage` resolves the agent's input to a stored key via
`slugify(name, collapse=True)`. So two stages whose names are equal — or merely
slug-equal (differ only in case/punctuation/whitespace) — would share a single
progress entry. Rejection therefore happens at load, in `Workflow.from_yaml`,
and discovery's existing per-file skip path (see
`test_discover_workflows.test_discover_skips_broken_and_loads_valid`) carries it
the rest of the way: a raising `from_yaml` causes the file to be skipped with a
warning naming it.
"""

import logging

import pytest

from beaker_notebook.lib.context import BeakerContext
from beaker_notebook.lib.workflow import Workflow


def _source_with_stages(stage_names: list[str], title: str = "Build Pipeline") -> dict:
    """A minimal, otherwise-valid `from_yaml` source with the given stage names."""
    return {
        "title": title,
        "agent_description": "agent desc",
        "human_description": "human desc",
        "example_prompt": "example",
        "stages": [
            {"name": name, "steps": [{"prompt": "do thing"}]}
            for name in stage_names
        ],
    }


def _yaml_with_stages(stage_names: list[str], title: str = "Build Pipeline") -> str:
    lines = [
        f"title: {title}",
        "agent_description: agent desc",
        "human_description: human desc",
        "example_prompt: example",
        "stages:",
    ]
    for name in stage_names:
        lines += [
            f"  - name: {name}",
            "    steps:",
            "      - prompt: do thing",
        ]
    return "\n".join(lines) + "\n"


def _make_context_class(workflow_dir):
    class _TestContext(BeakerContext):
        workflow_location = str(workflow_dir)

    return _TestContext


# --- from_yaml validation --------------------------------------------------


def test_distinct_stage_names_load_fine():
    """Positive control: a workflow with distinct stage names still parses."""
    wf = Workflow.from_yaml(_source_with_stages(["collect", "assess", "summarize"]))
    assert [stage.name for stage in wf.stages] == ["collect", "assess", "summarize"]


def test_exact_duplicate_stage_names_rejected():
    source = _source_with_stages(["collect", "summarize", "collect"])
    with pytest.raises(ValueError) as excinfo:
        Workflow.from_yaml(source)
    # A clear message that names the offending stage.
    assert "collect" in str(excinfo.value)
    assert "duplicate" in str(excinfo.value).lower()


def test_slug_variant_duplicate_stage_names_rejected():
    """Design decision: "duplicate" is defined by slug-equality, not exact
    string equality, because `update_workflow_stage` matches stage names via
    `slugify(..., collapse=True)`. "Collect Data" and "collect  data" resolve to
    the same progress slot, so they must be rejected at load too.

    If we ever decide duplicates should be exact-match only, this test is the one
    to flip.
    """
    source = _source_with_stages(["Collect Data", "collect  data"])
    with pytest.raises(ValueError) as excinfo:
        Workflow.from_yaml(source)
    assert "duplicate" in str(excinfo.value).lower()


# --- hidden normalization (#196 item 2) ------------------------------------


def test_hidden_defaults_to_false_when_absent():
    # from_yaml passes source.get("hidden", None); __post_init__ normalizes it.
    wf = Workflow.from_yaml(_source_with_stages(["collect"]))
    assert wf.hidden is False


def test_hidden_true_is_preserved():
    source = _source_with_stages(["collect"])
    source["hidden"] = True
    wf = Workflow.from_yaml(source)
    assert wf.hidden is True


# --- discovery skips a duplicate-stage workflow ----------------------------


def test_discover_skips_workflow_with_duplicate_stage_names(tmp_path, caplog):
    (tmp_path / "good.yaml").write_text(_yaml_with_stages(["collect", "summarize"]))
    (tmp_path / "dupe.yaml").write_text(
        _yaml_with_stages(["collect", "collect"], title="Dupe Stages")
    )

    ctx_cls = _make_context_class(tmp_path)
    with caplog.at_level(logging.WARNING):
        result = ctx_cls.discover_workflows()

    assert len(result) == 1
    titles = {wf.title for wf in result.values()}
    assert titles == {"Build Pipeline"}
    # Skipped with a warning naming the offending file (existing skip path).
    assert any("dupe.yaml" in rec.message for rec in caplog.records)
