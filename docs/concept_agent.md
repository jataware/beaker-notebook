---
layout: default
title: The Agent
parent: Key Concepts
nav_order: 2
has_toc: true
---

# The Agent

The **agent** is the AI assistant you interact with in Beaker. It can read and write code in your notebook, run that code in the subkernel, inspect the resulting state, and respond in natural language. You can talk to the agent from the chat interface or directly from a notebook cell.

The agent has full visibility into the notebook environment — every variable, every previous cell, every output — and uses that visibility to make informed decisions. When code fails, the agent can read the traceback and try to fix it. When a library it wants to use is not installed, it can install it on your behalf (subject to your configuration).

Each [context](concept_contexts.html) shapes the agent for its kind of work:

* **Instructions** — the prompt scaffolding that tells the agent how to think about your domain.
* **Tools** — function-like capabilities the agent can invoke (run code, query an API, fetch a file, ask the user a clarifying question).
* **Integrations** — see [Integrations](concept_integrations.html); the agent can use these to reach external data and services.
* **Workflows** — see [Workflows](concept_workflows.html); structured procedures the agent can follow for common tasks in the context.

Beaker's agent framework is [Archytas](https://github.com/jataware/archytas), a ReAct-style agent runtime that supports custom toolsets. If you want to customize the agent for your own context, see [Context Development](context_development.html).
