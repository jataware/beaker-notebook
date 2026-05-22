---
layout: default
title: Previews
parent: Key Concepts
nav_order: 6
has_toc: true
---

# Previews

A **preview** is a context-defined visualization of the current state of your notebook environment — what's loaded, what's interesting, what you might want to look at next. Previews appear in the preview panel of the Beaker UI, and update as the notebook state changes.

What a preview shows is entirely up to the context. A general-purpose context might show recently-defined variables and their types. A data-analysis context might render a thumbnail of the dataset you just loaded. A modeling context might plot the latest simulation output alongside the observed data.

You do not interact with previews directly — they appear automatically whenever the context generates one. If a context does not define previews, the preview panel is empty.

To define previews for your own context, see [Context Development](context_development.html).
