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

## Working with skills

The Integrations panel lets you view and manage **skills** directly:

* **Local skills** live on disk and are fully editable. You can create a new skill, edit its name, description, instructions (the `SKILL.md` body), and metadata, and add, edit, or remove its resource files (progressively-disclosed `reference`, `script`, and `asset` files, and code `examples`) that the agent loads on demand.
* **Remote skills** are defined by a URL pointing at a hosted `SKILL.md`. You select the *remote* source type and enter the URL; the fetched content is read-only. Use **Fetch** to preview a remote skill before saving.
* **Importing a skill** — click **Upload** (or drag a file onto the Integrations panel) to import a skill from a `SKILL.md` file or a `.zip` containing a skill directory. The skill's details are read from the file so you can review them before saving.

Skills **bundled with a context** are shown read-only — the panel opens them in a viewer rather than the editor — since a context owns its own skills. Everything else you added yourself is editable.

To build your own integration provider, see [Integration Development](integration_development.html).
