"""Tests for BeakerContext.discover_workflows (lib/context.py).

Covers issue #189 (crash-proof YAML discovery) and issue #193 (stable,
slug-derived workflow ids with collision rejection), plus the construction-time
auto-attach of a default workflow.
"""

import logging
from dataclasses import asdict
from unittest.mock import MagicMock

from beaker_notebook.lib.context import BeakerContext
from beaker_notebook.lib.utils import slugify


def _valid_yaml(title: str, *, is_context_default: bool = False) -> str:
    lines = [
        f"title: {title}",
        "agent_description: agent desc",
        "human_description: human desc",
        "example_prompt: example",
    ]
    if is_context_default:
        lines.append("is_context_default: true")
    lines += [
        "stages:",
        "  - name: stage_one",
        "    description: first stage",
        "    steps:",
        "      - prompt: do thing",
    ]
    return "\n".join(lines) + "\n"


def _make_context_class(workflow_dir):
    class _TestContext(BeakerContext):
        workflow_location = str(workflow_dir)

    return _TestContext


def test_discover_skips_broken_and_loads_valid(tmp_path, caplog):
    (tmp_path / "good_one.yaml").write_text(_valid_yaml("Build Pipeline"))
    (tmp_path / "good_two.yaml").write_text(_valid_yaml("Run Analysis"))
    # Malformed: missing required key (agent_description).
    (tmp_path / "broken.yaml").write_text("title: Broken Only\n")

    ctx_cls = _make_context_class(tmp_path)
    with caplog.at_level(logging.WARNING):
        result = ctx_cls.discover_workflows()

    assert len(result) == 2
    titles = {wf.title for wf in result.values()}
    assert titles == {"Build Pipeline", "Run Analysis"}
    assert any("broken.yaml" in rec.message for rec in caplog.records)


def test_discover_skips_invalid_yaml(tmp_path, caplog):
    (tmp_path / "good.yaml").write_text(_valid_yaml("Build Pipeline"))
    # Not parseable as YAML.
    (tmp_path / "bad.yaml").write_text("title: : :\n  - [unbalanced\n")

    ctx_cls = _make_context_class(tmp_path)
    with caplog.at_level(logging.WARNING):
        result = ctx_cls.discover_workflows()

    assert len(result) == 1
    assert any("bad.yaml" in rec.message for rec in caplog.records)


def test_discover_ids_are_stable_across_calls(tmp_path):
    (tmp_path / "one.yaml").write_text(_valid_yaml("Build Pipeline"))
    ctx_cls = _make_context_class(tmp_path)

    first = ctx_cls.discover_workflows()
    second = ctx_cls.discover_workflows()

    assert list(first.keys()) == list(second.keys())
    assert slugify("Build Pipeline") in first


def test_discover_id_is_slugified_title(tmp_path):
    (tmp_path / "one.yaml").write_text(_valid_yaml("Build Pipeline"))
    ctx_cls = _make_context_class(tmp_path)

    result = ctx_cls.discover_workflows()

    assert set(result.keys()) == {slugify("Build Pipeline")}


def test_discover_slug_collision_keeps_first(tmp_path, caplog):
    # Both titles slugify to the same value ("build_pipeline").
    (tmp_path / "a_first.yaml").write_text(_valid_yaml("Build Pipeline"))
    (tmp_path / "z_second.yaml").write_text(_valid_yaml("BUILD pipeline"))

    ctx_cls = _make_context_class(tmp_path)
    with caplog.at_level(logging.WARNING):
        result = ctx_cls.discover_workflows()

    assert len(result) == 1
    # glob order is filesystem-dependent; assert exactly one survived and a
    # collision warning naming the skipped file/title was logged.
    assert slugify("Build Pipeline") in result
    assert any("Duplicate workflow id" in rec.message for rec in caplog.records)


# --- construction-time default-workflow auto-attach ------------------------
#
# A workflow marked `is_context_default: true` must be attached during
# BeakerContext.__init__. attach_workflow -> send_response dereferences
# self.beaker_kernel, so the attach must run *after* beaker_kernel is assigned.
# Regression guard: an earlier refactor attached the default before
# self.beaker_kernel existed, raising AttributeError at construction.


class _StubAgent:
    """Minimal stand-in for BeakerAgent that __init__ can construct and poke."""

    def __init__(self, context, tools):
        self.context = context
        self.tools = tools
        self.chat_history = None

    def disable(self, *names):
        pass

    def set_auto_context(self, *args, **kwargs):
        pass


class _StubSubkernel:
    SLUG = "stub"
    tools: list = []

    def _resolve_procedure_dirs(self):
        return []


def _make_constructible_context_class(workflow_dir):
    class _TestContext(BeakerContext):
        AGENT_CLS = _StubAgent
        workflow_location = str(workflow_dir)

        def get_subkernel(self):
            return _StubSubkernel()

    return _TestContext


def test_default_workflow_attached_during_init(tmp_path):
    (tmp_path / "default.yaml").write_text(
        _valid_yaml("Build Pipeline", is_context_default=True)
    )
    (tmp_path / "other.yaml").write_text(_valid_yaml("Run Analysis"))

    ctx_cls = _make_constructible_context_class(tmp_path)
    kernel = MagicMock()

    # Constructing must not raise (the regression raised AttributeError because
    # the default was attached before self.beaker_kernel was set).
    ctx = ctx_cls(beaker_kernel=kernel)

    assert ctx.current_workflow_state is not None
    assert ctx.current_workflow_state.workflow_id == slugify("Build Pipeline")
    # The attach went through send_response on the (already-wired) kernel.
    # send_response forwards extra positional args (channel, parent_header, ...),
    # so match only the leading (stream, msg_type, content) triple.
    assert any(
        call.args[:3]
        == ("iopub", "update_workflow_state", asdict(ctx.current_workflow_state))
        for call in kernel.send_response.call_args_list
    )


def test_no_default_workflow_leaves_state_unattached(tmp_path):
    (tmp_path / "other.yaml").write_text(_valid_yaml("Run Analysis"))

    ctx_cls = _make_constructible_context_class(tmp_path)
    ctx = ctx_cls(beaker_kernel=MagicMock())

    assert ctx.current_workflow_state is None
