---
layout: default
title: Creating a Subkernel
parent: Subkernel Development
grand_parent: Development
nav_order: 1
has_toc: true
---

# Creating a Subkernel

Custom subkernels are distributed as Python packages and registered with Beaker through Python entry points, just like contexts. The Beaker CLI scaffolds the package layout for you.

## Scaffolding a new subkernel project

Start with a Beaker project:

```bash
beaker project new
```

and then add a subkernel to it:

```bash
beaker subkernel new
```

The wizard prompts for a name, class names, and a slug, and generates a package containing:

```
my_subkernel/
├── subkernel.py            # BeakerSubkernel (or CheckpointableBeakerSubkernel) subclass
└── procedures/
    ├── fetch_state.<ext>   # language-side helper script
    └── reflectors/
        ├── default.<ext>
        └── ...
```

## Installing for development

After scaffolding, install the package in editable mode so Beaker picks up your changes:

```bash
pip install -e .
```

The subkernel will be discovered automatically the next time Beaker starts. You can confirm it was registered with:

```bash
beaker subkernel list
```

For details on how reflectors fit into the subkernel, see [Reflectors](subkernel_reflectors.html).
