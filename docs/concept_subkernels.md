---
layout: default
title: Subkernels
parent: Key Concepts
nav_order: 3
has_toc: true
---

# Subkernels

A **subkernel** is the language runtime that actually executes the code in your Beaker notebook. When you run a code cell, Beaker passes the code through to its subkernel, which runs it the same way a stand-alone Jupyter kernel would.

The subkernel determines what language your notebook speaks and which libraries are available. Beaker ships with subkernels for **Python**, **R**, and **Julia**, and additional subkernels can be installed as Python packages — see [Adding Subkernels](adding_subkernels.html).

You do not usually choose a subkernel directly. Instead, you choose a [context](concept_contexts.html), and the context decides which subkernel to use. Most contexts work with the default Python subkernel; some contexts are tied to a particular language because their tools or pre-loaded objects only make sense there.

The subkernel runs in its own process with its own environment, so:

* Variables you define in one cell persist into later cells, just like a regular Jupyter notebook.
* The agent can introspect the subkernel's state (variables, imports) when deciding what code to generate.
* Switching contexts to one that uses a different language will start a fresh subkernel — your previous variables will not carry over.

To build your own subkernel for a new language, see [Subkernel Development](subkernel_development.html).
