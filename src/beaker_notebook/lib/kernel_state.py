"""
Kernel state schema and agent-payload rendering.

This module defines the canonical shape that all subkernels' ``fetch_state``
procedures should target, plus helpers for trimming the payload to a byte
budget and rendering it for the agent.

The shape is partially formalized: subkernels MUST emit ``local_names`` and
``variables`` (which may be empty), and MAY add additional top-level keys for
language-specific concepts the base schema doesn't model.
"""

import json
from typing import Any, Optional, TypedDict


class VariableDescription(TypedDict, total=False):
    """Per-variable detail surfaced under the ``variables`` key.

    Only ``type`` is required at runtime; the rest are best-effort and may be
    omitted by a reflector when not applicable.
    """

    type: str
    shape: Optional[str]
    size: Optional[int]
    summary: Optional[dict[str, Any]]
    sample: Optional[str]
    truncated: bool


class KernelStatePayload(TypedDict, total=False):
    """Canonical agent-facing kernel-state payload.

    ``local_names`` is a flat dict mapping every in-scope name to a short tag
    string (e.g. ``"module(`pandas`)"``, ``"DataFrame[5000x12]"``). It is the
    agent's primary signal for "what is already defined."

    ``variables`` carries richer entries, and SHOULD only include data
    variables (not modules/classes/functions, which are summarized in
    ``local_names``).

    Subkernels may add additional top-level keys for language-specific
    concepts; consumers should treat unknown keys as opaque pass-through.
    """

    local_names: dict[str, str]
    variables: dict[str, VariableDescription]


def apply_sample_budget(
    payload: KernelStatePayload,
    budget: int,
) -> KernelStatePayload:
    """Drop or truncate ``sample`` fields in ``variables`` to fit ``budget``.

    The budget is the maximum total characters of ``sample`` content across
    all variables in the payload. Variables are processed in iteration order;
    once the budget is exhausted, remaining variables get their ``sample``
    field stripped (replaced by None) and ``truncated`` set to True.

    A single variable whose ``sample`` exceeds the remaining budget on its own
    is truncated to fit, with ``truncated`` set to True.
    """
    if budget <= 0:
        # Strip every sample.
        for var in payload.get("variables", {}).values():
            if var.get("sample") is not None:
                var["sample"] = None
                var["truncated"] = True
        return payload

    remaining = budget
    for var in payload.get("variables", {}).values():
        sample = var.get("sample")
        if sample is None:
            continue
        if len(sample) <= remaining:
            remaining -= len(sample)
            continue
        if remaining > 0:
            var["sample"] = sample[:remaining]
            var["truncated"] = True
            remaining = 0
        else:
            var["sample"] = None
            var["truncated"] = True
    return payload


def render_agent_payload(payload: KernelStatePayload) -> str:
    """Render ``payload`` as the markdown block injected into the agent's
    chat history.

    Layout: ``local_names`` as a compact bullet list, ``variables`` as a JSON
    code block. Empty sections are omitted.
    """
    sections: list[str] = ["## Kernel state"]

    local_names = payload.get("local_names") or {}
    if local_names:
        body = "\n".join(f"- `{name}`: {tag}" for name, tag in local_names.items())
        sections.append(f"### Names in scope\n\n{body}")

    variables = payload.get("variables") or {}
    if variables:
        body = (
            "```application/json\n"
            + json.dumps(variables, indent=2, default=str)
            + "\n```"
        )
        sections.append(f"### Variables\n\n{body}")

    # Pass-through any extension keys the subkernel added that aren't
    # local_names or variables, as a generic JSON appendix. Keeps language-
    # specific extensions visible without forcing every consumer to handle
    # them explicitly.
    extras = {
        k: v
        for k, v in payload.items()
        if k not in ("local_names", "variables")
    }
    if extras:
        body = (
            "```application/json\n"
            + json.dumps(extras, indent=2, default=str)
            + "\n```"
        )
        sections.append(f"### Additional state\n\n{body}")

    return "\n\n".join(sections)
