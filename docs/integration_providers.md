---
layout: default
title: Providers
parent: Integration Development
grand_parent: Development
nav_order: 1
has_toc: true
---

# Integration Providers

A context's `integrations` field holds a list of providers — objects inheriting `BaseIntegrationProvider` or `MutableBaseIntegrationProvider`. A provider is responsible for enumerating its own integrations and exposing them to the agent and the front-end. If the `integrations` field is empty, no integrations are shown in the UI and the feature is effectively disabled for that context.

## Required methods

At minimum, an integration provider must implement:

```python
def list_integrations(self) -> list[Integration]:
    ...

def get_integration(self, integration_id: str) -> Integration:
    ...

def list_resources(self, integration_id: str, resource_type: Optional[str] = None) -> list[Resource]:
    ...

def get_resource(self, integration_id: str, resource_id: str) -> Resource:
    ...
```

A provider's identity is declared with class variables — `provider_type`, `slug`, and `display_name` — set on the provider class (not passed to `__init__`, which takes only an optional `id`).

Providers inheriting `MutableBaseIntegrationProvider` — designed to have integrations added, updated, or deleted at runtime — implement the following additional methods for those flows:

```python
def add_integration(self, **payload) -> Integration: ...
def update_integration(self, integration_id: str, **payload) -> Integration: ...
def remove_integration(self, integration_id: str, **payload) -> None: ...
def add_resource(self, integration_id: str, **payload) -> Resource: ...
def update_resource(self, integration_id: str, resource_id: str, **payload) -> Resource: ...
def remove_resource(self, integration_id: str, resource_id: str, **payload) -> None: ...
```

These are the methods behind the create/update/delete routes in the [REST API](integrations_api.html). `SkillIntegrationProvider` (local skills persisted to disk) and `MCPIntegrationProvider` are working examples of mutable providers.

See `beaker_notebook/lib/integrations/base.py` for the full base class.

How a provider stores its integrations and manages their lifecycle is entirely up to the provider implementation.

## Provider prompts

If no prompt is set, the default is the provider's docstring plus a string representation of each integration. You can override this in two ways:

1. **Set `prompt_instructions` on the provider** — appended to the default.
2. **Override the `prompt` property:**

```python
@property
def prompt(self) -> str:
    ...
```

The returned prompt is injected into the context and updated in place to track changes.

## Provider tools

Functions decorated with `@tool` on a provider become tools available to the agent when the context is loaded. These tools are bound to the provider instance (have access to `self`), so they can read and write the provider's stored integrations.

At a glance:

* The provider lists its integrations to the context.
* The agent reads the integrations list and decides whether to call one of the provider's `@tool` methods based on the user's query.

## Integration and Resource types

The `Integration` and `Resource` dataclasses, along with the specialized resource subclasses (`FileResource`, `ExampleResource`, `SkillMetadataResource`, `SkillInstructionsResource`, `SkillFileResource`, `SkillExampleResource`), are defined in `beaker_notebook/lib/integrations/types.py`. Resources are anything inheriting `Resource`, which carries:

* `resource_type` — a `ClassVar` defined on subclasses
* `resource_id` — a UUID
* `integration` — the UUID of the parent integration that owns the resource

For the REST API exposed by integrations to the front-end, see [REST API](integrations_api.html).
