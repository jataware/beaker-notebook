---
layout: default
title: Workflows
parent: Key Concepts
nav_order: 4
has_toc: true
---

# Workflows

A **workflow** is a named, multi-step procedure that the agent can follow to accomplish a recurring task. Workflows are defined by a [context](concept_contexts.html) and become available to the agent when that context is active.

Not every context uses workflows, but for contexts that do, they are often the most important feature: they capture domain expertise — the "right" way to do a thing — and let the agent execute that procedure consistently rather than reasoning from scratch every time.

For example, a context built around a particular modeling library might define workflows for:

* Loading and validating a new dataset
* Calibrating a model against observed data
* Producing a standard set of diagnostic plots
* Exporting results in the format the team expects

When you ask the agent to do something that matches a workflow, the agent can choose to follow that workflow rather than improvising a solution. This tends to produce more reliable, more reproducible results, and it lets domain experts encode their conventions once instead of explaining them in every conversation.

To define workflows for your own context, see [Context Development](context_development.html).
