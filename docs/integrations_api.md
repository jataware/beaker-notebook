---
layout: default
title: REST API
parent: Integration Development
grand_parent: Development
nav_order: 2
has_toc: true
---

# Integrations REST API

So that the frontend can use and interact with integrations on the context, the following routes are available, mapping to the Integration Provider methods.

Note: Integrations are exposed as a flattened map, so that no consumer is responsible for knowing what integration belongs to what provider - providers are abstracted away, except only in integration creation to say "create X integration on Y provider." As such, listing all integrations falls to the base context and does not need to be defined by the implementer.

* `GET /beaker/integrations/{session_id}`:
    * Method: `context.list_integrations()`

* `GET /beaker/integrations/{session_id}/{integration_id}`:
    * Method: `provider.get_integration(integration_id)`

* `GET /beaker/integrations/{session_id}/{integration_id}/all OR {resource_type}`:
    * Method: `provider.list_resources(integration_id)`

* `GET /beaker/integrations/{session_id}/{integration_id}/all OR {resource_type}/{resource_id}`:
    * Method: `provider.get_resource(integration_id, resource_id)`

* `POST /beaker/integrations/{session_id}/`:
    * Method: `provider.add_integration()`
    * Note: Target provider is specified through the POST body.

* `POST /beaker/integrations/{session_id}/{integration_id}`:
    * Method: `provider.update_integration(integration_id)`

* `POST /beaker/integrations/{session_id}/{integration_id}/{resource_type}`:
    * Method: `provider.add_resource(integration_id)`

* `POST /beaker/integrations/{session_id}/{integration_id}/{resource_type}/{resource_id}`:
    * Method: `provider.update_resource(integration_id, resource_id)`

* `DELETE /beaker/integrations/{session_id}/{integration_id}/{resource_type}/{resource_id}`:
    * Method: `provider.delete_resource(integration_id, resource_id)`

POST bodies are accessed through `**kwargs` on all of the respective methods above.

## REST API Implementation

The following routes are implemented via `context.call_in_context` which is a general RPC system for calling target functions on members of the context. This will likely not need to be used in any provider implementations.
