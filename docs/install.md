---
layout: default
title: Installing Beaker
parent: Getting Started
nav_order: 1
has_toc: true
---

# Installing Beaker

Installing Beaker is easy! All you need to do is run:

```bash
pip install beaker-notebook
```

This installs a CLI tool named `beaker` which allows you to work with and administer your local Beaker environment.

Now that you've got things installed and set up, to start a new Beaker notebook, just simply run:

```bash
beaker notebook
``` 

Your notebook server will start up and Beaker will be ready to use at [`localhost:8888`](http://localhost:8888).

## Configuration

When running as a local notebook, Beaker uses a configuration file to store your local settings, such as your preferred LLM provider.

You can locate, view, and update your Beaker configuration either via the Beaker UI or via the `beaker` cli command.

### Configuration file

The Beaker configuration can be stored either as user-wide configuration file, or as a per-directory configuration.
The user-wide configuration is usually located at `/home/{user}/.config/beaker.conf`, but you can confirm by running `beaker config find`.
Alternatively, a file named `.beaker.conf` can be placed in any directory. Running `beaker` commands (including starting a notebook)
in that directory (or any subdirectories in the tree), will use the local configuration file.

**Note:** `.beaker.conf` files may store your LLM provider API tokens. Take care to not accidentally expose this file, and exclude it from
git, etc.

### Viewing/Updating

In the UI, the configuration is accessible via the `Config` side-panel. When you make changes and save the config, the Beaker will update the active configuration file, or create a new user configuration file.

Next, you'll run `beaker config update` to set up your configuration. This will create a `beaker.conf` file in your home directory's `.config` folder. You can leave everything as the default except for the `LLM_SERVICE_TOKEN` which you'll need to set to your OpenAI API (or other LLM provider) key.

## Next steps

* To install a prebuilt context (for example, a domain-specific context published by your team), see [Adding Contexts](adding_contexts.html).
* To install a prebuilt subkernel that adds language support beyond Python, R, and Julia, see [Adding Subkernels](adding_subkernels.html).
* To take a first tour of the notebook interface, see [Your First Notebook](your_first_notebook.html).
* If you want to *build* your own context or subkernel, see [Development](development.html).

## Developer setup

For developers interested in modifying Beaker itself or contributing to it, clone the repository and run:

```bash
make dev
```

This will start Beaker in development mode, which automatically reloads when you make changes to the code so you can quickly iterate on changes to the core codebase.
