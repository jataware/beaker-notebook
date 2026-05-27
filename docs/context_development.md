---
layout: default
title: Context Development
parent: Development
nav_order: 1
has_toc: false
has_children: true
---

# Context Development

A context is the primary unit of customization in Beaker. It defines what subkernel runs, what tools the agent has access to, what custom messages flow between the front-end and the kernel, and what previews the notebook renders. The pages in this section cover authoring each of those pieces.

If you have not yet read the conceptual overview, see [Key Concepts > Contexts](concept_contexts.html) first.

## Setting a context from a front-end

External applications (such as a custom front-end) set a context by sending a `context_setup_request` message to the Beaker kernel:

```json
{
  "subkernel": "<subkernel slug>",
  "context": "<context slug>",
  "context_info": {"<json payload of any settings/info required to start the context>"}
}
```

The list of available subkernels and contexts depends on what has been installed. The contents of `context_info` are defined by the context itself. The Beaker service exposes a discovery endpoint at `http://{jupyter_url}/beaker/contexts/` that returns the installed contexts and which subkernels each supports.

## Tool toggling

Tools on the agent can be toggled individually using either an environment variable or a class attribute. To toggle a tool, create an attribute on your context class or set a variable in your environment named `TOOL_ENABLED_{YOUR_TOOL_NAME_IN_UPPER_CASE}`. `True` enables the tool; `False` disables it. If both are set, the class attribute wins. For example, the environment variable `TOOL_ENABLED_ASK_USER=false` is overridden by:

```python
class FooContext(BaseContext):
    TOOL_ENABLED_ASK_USER = True
    ...
```

If no toggle is set for a tool, it defaults to enabled.
