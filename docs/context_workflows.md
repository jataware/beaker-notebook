---
layout: default
title: Workflows
parent: Context Development
grand_parent: Development
nav_order: 6
has_toc: true
---

# Workflows

A workflow is a named, multi-step procedure that the agent can follow when accomplishing a recurring task in your context. Defining workflows lets you encode domain expertise — the "right" way to do a thing — once, so the agent can execute it consistently rather than improvising every time.

For the conceptual overview, see [Key Concepts > Workflows](concept_workflows.html).

> This page is a placeholder. Full guidance on defining workflows for a context is forthcoming. In the meantime, `beaker_kernel.lib.workflow` and the `workflow_location` attribute on `BeakerContext` are the entry points; the default context's tests in `tests/test_workflow_tools.py` show several workflow patterns in use.
