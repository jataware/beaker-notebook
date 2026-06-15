"""Tests for workflow extraction in lib/context_dump.py.

Focused on the `agent_instructions` field: the dump must succeed whether or not
a workflow defines it, and the value must be carried through to the extracted
output when present.
"""

from beaker_notebook.lib.context_dump import _extract_workflows


# A distinctive sentinel so presence/absence assertions are unambiguous.
AGENT_INSTRUCTIONS = "SECRET-AGENT-GUIDANCE: prefer pandas over polars for this task."

WORKFLOW_WITH_INSTRUCTIONS = """
title: With Instructions
agent_description: ad
human_description: hd
example_prompt: ep
agent_instructions: |
  {instructions}
stages:
  - name: s1
    steps:
      - do a thing
""".format(instructions=AGENT_INSTRUCTIONS)

WORKFLOW_WITHOUT_INSTRUCTIONS = """
title: Without Instructions
agent_description: ad
human_description: hd
example_prompt: ep
stages:
  - name: s1
    steps:
      - do a thing
"""


# Defined at module level so inspect.getfile(context_cls) resolves to this test
# file. With an absolute `workflow_location`, _extract_workflows reads YAML from
# that directory directly.
class _FakeContext:
    workflow_location = None


def _make_context_cls(workflows_dir):
    cls = type("_FakeWorkflowContext", (_FakeContext,), {})
    cls.__module__ = _FakeContext.__module__
    cls.workflow_location = str(workflows_dir)
    return cls


def _write_workflow(workflows_dir, name, content):
    path = workflows_dir / name
    path.write_text(content)
    return path


def test_extract_workflows_includes_agent_instructions(tmp_path):
    workflows_dir = tmp_path / "workflows"
    workflows_dir.mkdir()
    _write_workflow(workflows_dir, "with.yaml", WORKFLOW_WITH_INSTRUCTIONS)

    context_cls = _make_context_cls(workflows_dir)
    all_workflows: dict = {}

    refs = _extract_workflows(context_cls, str(tmp_path), all_workflows)

    assert len(refs) == 1
    assert len(all_workflows) == 1
    extracted = next(iter(all_workflows.values()))
    assert extracted["title"] == "With Instructions"
    assert extracted["agent_instructions"].strip() == AGENT_INSTRUCTIONS


def test_extract_workflows_without_agent_instructions(tmp_path):
    workflows_dir = tmp_path / "workflows"
    workflows_dir.mkdir()
    _write_workflow(workflows_dir, "without.yaml", WORKFLOW_WITHOUT_INSTRUCTIONS)

    context_cls = _make_context_cls(workflows_dir)
    all_workflows: dict = {}

    # The dump must succeed even when the field is absent.
    refs = _extract_workflows(context_cls, str(tmp_path), all_workflows)

    assert len(refs) == 1
    assert len(all_workflows) == 1
    extracted = next(iter(all_workflows.values()))
    assert extracted["title"] == "Without Instructions"
    # Field is always present in the output, defaulting to None.
    assert "agent_instructions" in extracted
    assert extracted["agent_instructions"] is None


def test_extract_workflows_mixed(tmp_path):
    """Both kinds of workflow extract successfully side by side."""
    workflows_dir = tmp_path / "workflows"
    workflows_dir.mkdir()
    _write_workflow(workflows_dir, "with.yaml", WORKFLOW_WITH_INSTRUCTIONS)
    _write_workflow(workflows_dir, "without.yaml", WORKFLOW_WITHOUT_INSTRUCTIONS)

    context_cls = _make_context_cls(workflows_dir)
    all_workflows: dict = {}

    refs = _extract_workflows(context_cls, str(tmp_path), all_workflows)

    assert len(refs) == 2
    assert len(all_workflows) == 2
    by_title = {w["title"]: w for w in all_workflows.values()}
    assert by_title["With Instructions"]["agent_instructions"].strip() == AGENT_INSTRUCTIONS
    assert by_title["Without Instructions"]["agent_instructions"] is None
