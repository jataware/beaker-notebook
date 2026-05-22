---
# This file is a page template. The leading underscore in the filename causes
# Jekyll to skip it during site generation, so it will not appear in the
# rendered documentation. To create a new docs page, copy this file:
#
#     cp _base.md my_new_page.md
#
# and then fill in the front matter and content below.

layout: default

# Display title of the page in the sidebar and as the H1 if you do not provide
# one in the body.
title: Your Page Title

# Top-level section this page belongs to. One of:
#   - Getting Started
#   - Key Concepts
#   - Development
#   - CLI Reference
# Omit `parent` entirely for a page that should appear at the top level of the
# navigation alongside the section index pages.
parent: Development

# If this page is itself a child of a sub-section page (three levels deep),
# set `grand_parent` to the top-level section. For example, pages under
# "Context Development" use `parent: Context Development` and
# `grand_parent: Development`. The theme supports up to 3 levels of nesting;
# 4 levels deep is not supported.
# grand_parent: Development

# Position within the parent section. Lower numbers appear first.
nav_order: 99

# Whether to render a table of contents at the top of the page.
has_toc: true

# Set to true only if this page has child pages of its own.
has_children: false
---

# Your Page Title

Replace this paragraph with your page content. Use standard Markdown; the
just-the-docs theme styles headings, lists, tables, code blocks, and callouts
automatically.

When cross-linking to other pages in this documentation, use the rendered
`.html` URL (for example `[Contexts](concept_contexts.html)`), not the source
`.md` filename, so the links resolve correctly on the published site.
