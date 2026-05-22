---
layout: default
title: beaker-ts
parent: UI Development
grand_parent: Development
nav_order: 1
has_toc: true
---

# beaker-ts TypeScript library

`beaker-ts` is a low-level TypeScript library for embedding Beaker into your own front-end application. It provides session management, message handling, a lightweight reactive notebook model, and rendering utilities for working with a running Beaker kernel from the browser.

## What beaker-ts provides

* **Sessions** — creating and managing Beaker sessions, including connecting to an existing kernel or spinning up a new one, sending and receiving messages directly to the kernel, and tracking kernel status.
* **A lightweight reactive notebook** — interfaces and classes for all standard Jupyter cell types plus a Beaker-specific "LLM Query" cell for interactions with the agent. Tested to be reactive in React and Vue. Exportable to standard Jupyter `.ipynb` format.
* **Rendering** — full rendering of all output types registered with Jupyter, with a pluggable system for adding custom MIME renderers.
* **History tracking** — records the actions taken in a notebook to support future save/replay and rollback workflows.
* **Utilities** — message helpers, type guards, and small utilities for working with Jupyter messages and notebook cells.

The library is organized into modules — `session`, `notebook`, `history`, `util`, `render` — that correspond to each of these areas. Full per-module API reference, generated from the source, is available at:

[Beaker-ts API documentation]({{ site.baseurl }}/beaker-ts/)

## When to use beaker-ts

If you are building a custom front-end that talks to a Beaker kernel, `beaker-ts` is the right starting point — it handles the Jupyter protocol details, session lifecycle, and notebook model so you can focus on your own UI.

If you are extending the default Beaker UI (the notebook you see when you run `beaker notebook`), you will want to work with the `beaker-vue` component library or the `beaker-ui` application instead. Both are built on top of `beaker-ts` and are part of this repository.
