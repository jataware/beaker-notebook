---
layout: default
title: UI Development
parent: Development
nav_order: 4
has_toc: false
has_children: true
---

# UI Development

Beaker's front-end is built from three layered TypeScript packages:

* **beaker-ts** — a low-level TypeScript library for embedding Beaker into your own front-end application. It provides session management, message handling, a lightweight reactive notebook model, and rendering utilities.
* **beaker-vue** — a Vue 3 component library built on top of `beaker-ts`. Contains the cell, panel, and session components used by the default Beaker UI.
* **beaker-ui** — the default Beaker user interface, which composes `beaker-vue` components into the notebook, chat, dev, and integrations pages you see when you run `beaker notebook`.

If you are embedding Beaker into your own application, start with [beaker-ts](beaker_ts.html). If you are modifying the default UI, the `beaker-vue` and `beaker-ui` packages are the place to look — they are not yet documented here in detail.
