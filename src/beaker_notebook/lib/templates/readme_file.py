from pathlib import Path
from hatchling.plugin import hookimpl
from hatch.template.plugin.interface import TemplateInterface
from hatch.template import File
from hatch.template.files_default import PyProject

from . import JinjaTemplateFile, TemplateFile, PathTemplate
from .paths import package_name, context_subdir


class ReadmeFile(JinjaTemplateFile):
    PATH_PARTS = [
        'README.md',
    ]

    TEMPLATE = """\
# {{ project_name }} - an extension for [Beaker notebooks](https://github.com/jataware/beaker-kernel)

[![PyPI - Version](https://img.shields.io/pypi/v/{{ project_name_normalized }}.svg)](https://pypi.org/project/{{ project_name_normalized }})
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/{{ project_name_normalized }}.svg)](https://pypi.org/project/{{ project_name_normalized }})
-----

## Table of Contents

- [About Beaker](#about-beaker)
- [Installation](#installation)


## About Beaker

Beaker provides Contextually-aware notebooks with built-in AI assistant. It is built atop Jupyter, leveraging the deep Jupyter ecosystem.

It consists of multiple aspects, including:
- A server for hosting/running Beaker/Jupyter sessions.
- The Beaker kernel, an advanced Jupyter Kernel.
- Beaker-TS, a TypeScript/JavaScript library.
- A Vue based, reactive, extensible UI interface.
- Beaker-Vue, a Vue3 component library for building your own UIs with minimal hassle.

Beaker can be extended with new [contexts](https://jataware.github.io/beaker-kernel/contexts.html) and [subkernels](https://jataware.github.io/beaker-kernel/subkernels.html)

Learn more in the [Beaker documentation](https://jataware.github.io/beaker-kernel/).

## Installation

To add any contained contexts or subkernels to Beaker, you simply need to install this package. The provided elements will be available in Beaker upon next start.

### PyPI install (if deployed)
```console
pip install {{ project_name_normalized }}
```

### beaker CLI (installs project in dev mode)
```console
beaker project update {{ project_name_normalized }}
```

### local pip dev mode install
```console
cd {{ project_name_normalized }}
pip install -e .
```

### local pip install
```console
cd {{ project_name_normalized }}
pip install .
```

### Note
Some changes, such as adding or moving a context require updating/reinstalling the project.
You should run `beaker project update` if you encounter issues after making updates to the project.

"""
