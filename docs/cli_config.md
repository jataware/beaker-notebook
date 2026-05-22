---
layout: default
title: config
parent: CLI Reference
nav_order: 5
has_toc: true
---

# beaker config

The `beaker config` commands locate, view, and update your Beaker configuration file.

| Command | Purpose |
|---|---|
| `beaker config find` | Print the path to the active configuration file (user-wide or per-directory). |
| `beaker config update` | Interactively update the active configuration. Creates a user-wide config file if none exists. |

Beaker reads configuration from either a user-wide file (typically `~/.config/beaker.conf`) or a per-directory `.beaker.conf` file in the current directory tree. The configuration stores settings like your preferred LLM provider and any provider API keys, so be careful not to commit `.beaker.conf` files to version control.

> This page is a placeholder. Run `beaker config --help` for the authoritative list of options.
