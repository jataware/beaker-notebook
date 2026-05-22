---
layout: default
title: Contexts
parent: Key Concepts
nav_order: 1
has_toc: true
---

# Contexts

A **context** is what tells Beaker *how to be helpful for a particular kind of work*. When you set a context, you are choosing the language Beaker runs (its subkernel), the tools the agent has access to, any data or objects that should be pre-loaded into your environment, and the instructions that shape how the agent thinks about your requests.

Beaker ships with a default context that works well for general-purpose programming and data analysis. Custom contexts can be installed as Python packages — see [Adding Contexts](adding_contexts.html) — and you can switch between installed contexts at any time from the context selector in the notebook UI.

Some examples of what a context might add:

* **Domain knowledge** — a context for working with a specific modeling library can pre-load helpful objects and teach the agent that library's conventions.
* **External data** — a context can wire up access to a database, an API, or a private dataset, exposed as [integrations](concept_integrations.html) the agent can use.
* **Custom tools** — a context can give the agent specialized tools (run a simulation, query a knowledge base, render a domain-specific visualization).
* **Workflows** — a context can ship [workflows](concept_workflows.html) the agent can follow when accomplishing common tasks.

To build your own context, see [Context Development](context_development.html).
