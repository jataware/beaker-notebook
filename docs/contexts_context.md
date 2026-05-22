---
layout: default
title: Creating a New Context
parent: Context Development
grand_parent: Development
nav_order: 1
has_toc: true
---

We've tried to make creating a new context as easy as possible by providing some helper utilities in the Beaker CLI for context management. First, you can list the available contexts with `beaker context list`. You should see the default context that comes pre-installed with Beaker.

# Creating a New Context

As Beaker contexts are installed via Python packages, the first step is to create a Beaker project using the beaker cli command `beaker project new`:

```pre
~/dev$ beaker project new
Project name: beaker-hypercube
Would you like to provide additional dependencies now? [y/N]: y
Leave blank to finish.
Dependency definition: xarray~=2024.10.0
Dependency definition: pandas
Dependency definition: numpy
Dependency definition: 
Would you like to include an example context? [Y/n]: 
Name for the context [beaker-hypercube]: hypercube
Base Name for generated classes [Hypercube]: 
Sub-directory to write context files [beaker_hypercube_context]: hypercube_context

Generating project files...
beaker-hypercube
├── src
│   └── beaker_hypercube
│       ├── hypercube_context
│       │   ├── __init__.py
│       │   ├── agent.py
│       │   └── context.py
│       ├── __about__.py
│       └── __init__.py
├── tests
│   └── __init__.py
├── LICENSE.txt
├── README.md
└── pyproject.toml
Done.

Would you like to install the new project in dev mode in your current environment? [y/N]: y

Installing beaker-hypercube from directory dev/beaker-hypercube
Obtaining file://dev/beaker-hypercube
  Installing build dependencies ... done
...
Successfully installed beaker-hypercube-0.0.1 pandas-2.2.3 xarray-2024.10.0

[notice] A new release of pip is available: 24.2 -> 24.3.1
[notice] To update, run: python3.10 -m pip install --upgrade pip

Note:
  Some changes, such as adding or moving a context require updating/reinstalling the project.
  You may need to run 'beaker project update' if you encounter issues after making updates to the project.
~/dev$
```

From here on out, your work is to customize the `agent.py` and `context.py` files to meet your needs. Once you're ready to give it a shot, you can run `beaker project update` or `pip install -e .` to install your context in development mode.

**Note:** A Beaker project can have more than 1 context per project. To add an additional context, you can run `beaker context new` inside your project directory and you will be walked through a similar wizard for adding the new context.


# Building a Context Package

Beaker projects use [Hatch](https://hatch.pypa.io/latest/) as a build system. It is important to use Hatch as Beaker ships with a custom builder that ensures that Contexts and Subkernels are properly packaged so that they will be registered during install.

To build your package, simply run `hatch build` and Hatch will build a wheel and source file located in the local `dist/` directory:

```pre
~/dev/beaker-hypercube$ hatch build
────── sdist ──────
dist/beaker_hypercube-0.0.1.tar.gz
────── wheel ──────
Found the following contexts:
  'hypercube': HypercubeContext in package beaker_hypercube.hypercube_context.context

dist/beaker_hypercube-0.0.1-py3-none-any.whl
~/dev/beaker-hypercube$ 
```

You will notice that the build script lists any Beaker Contexts found.

If you are [publishing your package to PyPi](https://hatch.pypa.io/latest/publish/), you can do so with the command `hatch publish`. 

Please see the [Hatch Documentation](https://hatch.pypa.io/latest/) if you have any questions regarding Hatch.
