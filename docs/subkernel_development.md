---
layout: default
title: Subkernel Development
parent: Development
nav_order: 2
has_toc: false
has_children: true
---

# Subkernel Development

A subkernel adds a language runtime to Beaker. Beaker ships with Python, R, and Julia subkernels out of the box; this section covers building your own.

If you have not yet read the conceptual overview, see [Key Concepts > Subkernels](concept_subkernels.html) first.

Each subkernel is a Python package, discovered through Python entry points. The package layout is:

```
my_subkernel/
├── subkernel.py            # BeakerSubkernel (or CheckpointableBeakerSubkernel) subclass
└── procedures/
    ├── fetch_state.<ext>   # language-side helper script(s)
    └── reflectors/
        ├── default.<ext>   # per-type reflectors used to summarize variables
        └── ...
```

The CLI scaffolds this layout for you; see [Creating a Subkernel](subkernel_creating.html) to get started.
