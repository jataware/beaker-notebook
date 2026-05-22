---
layout: default
title: Reflectors
parent: Subkernel Development
grand_parent: Development
nav_order: 2
has_toc: true
---

# Reflectors

A **reflector** is a per-type variable inspector that runs inside a subkernel and produces a structured summary suitable for inclusion in the agent's prompt. Reflectors are how Beaker tells the agent "here's what's in your environment right now" without dumping raw repr output.

## Why per-type reflectors

A naive `repr()` of a large DataFrame or NumPy array would blow out the prompt window. Per-type reflectors let each kind of variable be summarized in a way that captures its identity (shape, columns, dtype, length, key sample values) while staying compact.

## How they are organized

Each subkernel package ships a `procedures/reflectors/` directory containing one file per type the subkernel wants to handle specially:

```
my_subkernel/procedures/reflectors/
├── default.<ext>      # fallback for any type not otherwise handled
├── primitive.<ext>    # ints, floats, bools, strings
├── sequence.<ext>     # lists, tuples
├── mapping.<ext>      # dicts
├── dataframe.<ext>    # pandas.DataFrame, etc.
└── ...
```

The built-in Python, Julia, and R subkernels ship reflectors for the most common types in each language (the Python subkernel includes `class`, `dataframe`, `function`, `mapping`, `ndarray`, `primitive`, `sequence`, `series`, `string`; the Julia and R subkernels carry analogous sets). Use those as templates when writing reflectors for your own subkernel.

## Writing a reflector

A reflector is a snippet of code in the subkernel's language. It receives a variable and returns a structured summary (typically a dict with fields like `type`, `shape`, `summary`, and possibly a small sample). The exact contract is captured by the `default.<ext>` reflector in each built-in subkernel — start there.

For the Python side that orchestrates reflection, see `beaker_kernel.lib.reflector`.
