---
layout: default
title: Integrations
parent: Key Concepts
nav_order: 5
has_toc: true
---

# Integrations

An **integration** is a thing the agent can reach outside the notebook environment to help accomplish a task — typically an external data source, API, library, or bundle of domain knowledge. You generally do not use an integration directly; the agent chooses to use it when relevant to your request.

At a high level, an integration can be:

* A remote or local **web API**
* A remote or local **dataset or database**
* A **library or suite of tools** the agent should know about
* A **skill** — a bundle of instructions, examples, and supporting files that augments the agent for a specific kind of task

A [context](concept_contexts.html) defines which integrations are available, either statically (the context author bakes them in) or dynamically (you add and remove integrations at runtime from the Integrations panel in the UI). If a context has no integrations, the Integrations panel is hidden.

You will encounter integrations primarily in two places:

* In the **Integrations panel**, which lists what's available in your current context and lets you add or configure them.
* In conversation with the agent, when it tells you it's looking something up via an integration, fetching data, or following the instructions in a skill.

To build your own integration provider, see [Integration Development](integration_development.html).
