---
layout: default
title: Adding Subkernels
parent: Getting Started
nav_order: 3
has_toc: true
---

# Adding Subkernels

> Looking to **build** your own subkernel? See [Subkernel Development](subkernel_development.html) instead. This page is about installing subkernels that someone else has already built.

Beaker ships with subkernels for Python, R, and Julia out of the box. Additional language support is distributed as Python packages, discovered automatically through Python entry points — much like contexts.

To install a hypothetical Rust subkernel published to PyPI:

```bash
pip install beaker-rust
```

The new subkernel will be available the next time you start Beaker. You can confirm it was registered by running:

```bash
beaker subkernel list
```

## Installing from a wheel or local checkout

The same install paths apply as for contexts:

```bash
# from a wheel
pip install ./beaker_rust-0.1.0-py3-none-any.whl

# from a Git URL
pip install git+https://github.com/example/beaker-rust.git

# from a local checkout (editable install)
pip install -e ./beaker-rust
```

## Underlying language runtime

A subkernel package installs the Beaker glue for a language, but it does not necessarily install the language runtime itself. For example, a Rust subkernel will likely require that you have a working Rust toolchain and the underlying Jupyter kernel for Rust already installed. Check the subkernel's own documentation for any prerequisites.

## Conceptual background

For an introduction to what a subkernel is and how Beaker uses it, see [Key Concepts > Subkernels](concept_subkernels.html).
