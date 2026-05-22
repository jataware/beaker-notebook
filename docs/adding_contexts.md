---
layout: default
title: Adding Contexts
parent: Getting Started
nav_order: 2
has_toc: true
---

# Adding Contexts

> Looking to **build** your own context? See [Context Development](context_development.html) instead. This page is about installing contexts that someone else has already built.

Contexts are distributed as Python packages and discovered automatically through Python entry points. Installing a context is just a `pip install`.

For example, to install a Beaker context designed for working with the PySB modeling library:

```bash
pip install beaker-pysb
```

The context will then be available the next time you start Beaker. You can confirm it was registered by running:

```bash
beaker context list
```

## Installing from a wheel or local checkout

You can also install a context directly from a wheel file, a Git URL, or a local directory:

```bash
# from a wheel
pip install ./beaker_pysb-0.1.0-py3-none-any.whl

# from a Git URL
pip install git+https://github.com/example/beaker-pysb.git

# from a local checkout (editable install — useful while iterating)
pip install -e ./beaker-pysb
```

An editable install (`pip install -e .`) is particularly useful when you are tracking a context that is still being developed — your environment picks up changes the next time you set the context on a session, without reinstalling.

## Conceptual background

For an introduction to what a context is and what it does for you, see [Key Concepts > Contexts](concept_contexts.html).
