"""
Context dump module for extracting context metadata into the interchange format.

Produces JSON output suitable for ingestion into BeakerHub's database.
"""
import hashlib
import inspect
import json
import logging
import os
from datetime import datetime, timezone
from importlib.metadata import entry_points, packages_distributions
from pathlib import Path
from typing import Any, Optional

import yaml

from beaker_notebook.lib.context import BeakerContext
from beaker_notebook.lib.integrations.base import BaseIntegrationProvider
from beaker_notebook.lib.workflow import Workflow

logger = logging.getLogger(__name__)

DUMP_VERSION = "1.0"


def generate_context_dumps(
    context_filter: Optional[str] = None,
    package_filter: Optional[str] = None,
) -> list[dict[str, Any]]:
    """
    Discover all installed contexts and produce interchange-format dumps grouped by package.

    Args:
        context_filter: If set, only include contexts matching this slug.
        package_filter: If set, only include contexts from this package name.

    Returns:
        List of ContextDump dicts, one per package.
    """
    # Phase 1: Discover contexts and group by package
    package_groups: dict[str, dict[str, Any]] = {}
    # package_groups[package_name] = {
    #     "version": str,
    #     "source_path": str,
    #     "context_classes": [(slug, context_cls), ...],
    # }

    # Primary: entry points (has distribution metadata)
    eps = entry_points(group="beaker.contexts")
    for ep in eps:
        try:
            context_cls = ep.load()
        except Exception as e:
            logger.warning(f"Failed to load context entry point '{ep.name}': {e}")
            continue

        slug = getattr(context_cls, "SLUG", ep.name)
        if context_filter and slug != context_filter:
            continue

        pkg_name = ep.dist.name if ep.dist else None
        pkg_version = ep.dist.version if ep.dist else None

        if pkg_name is None:
            logger.warning(f"Context '{slug}' has no distribution metadata, skipping.")
            continue

        if package_filter and pkg_name != package_filter:
            continue

        if pkg_name not in package_groups:
            source_path = _resolve_source_path(context_cls)
            package_groups[pkg_name] = {
                "version": pkg_version or "unknown",
                "source_path": source_path,
                "context_classes": [],
            }

        package_groups[pkg_name]["context_classes"].append((slug, context_cls))

    # Fallback: legacy JSON-mapped contexts (no EntryPoint.dist)
    _discover_legacy_contexts(package_groups, context_filter, package_filter, eps)

    # Phase 2: Build dumps per package
    dumps = []
    for pkg_name, pkg_info in package_groups.items():
        try:
            dump = _build_package_dump(pkg_name, pkg_info)
            dumps.append(dump)
        except Exception as e:
            logger.error(f"Failed to build dump for package '{pkg_name}': {e}")

    return dumps


def _resolve_source_path(context_cls: type) -> str:
    """Resolve the source path for a context class's package."""
    try:
        class_file = inspect.getfile(context_cls)
        # Walk up to find the package root (directory containing __init__.py
        # that is a top-level package)
        path = Path(class_file).resolve().parent
        while (path.parent / "__init__.py").exists():
            path = path.parent
        return str(path)
    except (TypeError, OSError):
        return "unknown"


def _discover_legacy_contexts(
    package_groups: dict[str, dict],
    context_filter: Optional[str],
    package_filter: Optional[str],
    eps,
) -> None:
    """
    Discover contexts from legacy JSON mappings that weren't found via entry points.
    """
    from beaker_notebook.lib.autodiscovery import autodiscover

    ep_names = {ep.name for ep in eps}
    all_contexts = autodiscover("contexts")

    # Reverse lookup: module -> package name
    pkg_dist_map = None

    for slug, context_cls in all_contexts.items():
        if slug in ep_names:
            # Already handled via entry points
            continue

        if context_filter and slug != context_filter:
            continue

        # Try to resolve package from module
        module_name = context_cls.__module__
        top_level = module_name.split(".")[0]

        if pkg_dist_map is None:
            try:
                pkg_dist_map = packages_distributions()
            except Exception:
                pkg_dist_map = {}

        pkg_names = pkg_dist_map.get(top_level, [])
        if pkg_names:
            pkg_name = pkg_names[0]
        else:
            pkg_name = top_level
            logger.warning(
                f"Context '{slug}' loaded via legacy mapping; "
                f"could not resolve package from module '{module_name}'. "
                f"Using '{pkg_name}' as package name."
            )

        if package_filter and pkg_name != package_filter:
            continue

        if pkg_name not in package_groups:
            source_path = _resolve_source_path(context_cls)
            # Try to get version
            version = "unknown"
            try:
                from importlib.metadata import version as get_version
                version = get_version(pkg_name)
            except Exception:
                pass

            package_groups[pkg_name] = {
                "version": version,
                "source_path": source_path,
                "context_classes": [],
            }

        package_groups[pkg_name]["context_classes"].append((slug, context_cls))


def _build_package_dump(pkg_name: str, pkg_info: dict) -> dict[str, Any]:
    """Build a complete ContextDump dict for a single package."""
    context_classes: list[tuple[str, type[BeakerContext]]] = pkg_info["context_classes"]

    # Collect integrations and workflows across all contexts in this package,
    # deduplicating by UUID (integrations) and file_path (workflows).
    all_integrations: dict[str, dict[str, Any]] = {}  # uuid -> integration dump
    all_workflows: dict[str, dict[str, Any]] = {}  # file_path -> workflow dump
    context_records: list[dict[str, Any]] = []

    for slug, context_cls in context_classes:
        # Extract integrations for this context
        context_integration_uuids = _extract_integrations(
            context_cls, pkg_info["source_path"], all_integrations
        )

        # Extract workflows for this context
        context_workflow_refs = _extract_workflows(
            context_cls, pkg_info["source_path"], all_workflows
        )

        # Extract language slugs
        language_slugs = _extract_language_slugs(context_cls)

        # Build context record
        context_record = _build_context_record(
            context_cls=context_cls,
            slug=slug,
            integration_uuids=context_integration_uuids,
            workflow_refs=context_workflow_refs,
            language_slugs=language_slugs,
        )
        context_records.append(context_record)

    return {
        "dump_version": DUMP_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "package": {
            "name": pkg_name,
            "version": pkg_info["version"],
            "source_path": pkg_info["source_path"],
        },
        "integrations": list(all_integrations.values()),
        "api_keys": [],  # TODO: No mechanism to enumerate required API keys yet
        "workflows": list(all_workflows.values()),
        "contexts": context_records,
    }


def _find_integration_providers(
    context_cls: type[BeakerContext],
) -> list[BaseIntegrationProvider]:
    """
    Instantiate integration providers for a context without running full context init.

    Mirrors BeakerContext.__init__: combines the default providers (currently
    a SkillIntegrationProvider) with any declared via the class-level
    INTEGRATION_PROVIDERS attribute.
    """
    from beaker_notebook.lib.integrations.skill import SkillIntegrationProvider

    providers: list[BaseIntegrationProvider] = [SkillIntegrationProvider("Default Skills")]

    try:
        providers.extend(context_cls.extra_integration_providers())
    except Exception as e:
        logger.warning(
            f"Failed to instantiate INTEGRATION_PROVIDERS for context "
            f"'{getattr(context_cls, 'SLUG', '?')}': {e}"
        )

    return providers


def _extract_integrations(
    context_cls: type[BeakerContext],
    package_source_path: str,
    all_integrations: dict[str, dict[str, Any]],
) -> list[str]:
    """
    Extract integrations from a context class's integration providers.
    Deduplicates by UUID into all_integrations. Returns list of UUIDs for this context.
    """
    context_uuids: list[str] = []
    providers = _find_integration_providers(context_cls)

    for provider in providers:
        try:
            integrations = provider.list_integrations()
        except Exception as e:
            logger.warning(
                f"Failed to list integrations for provider "
                f"'{getattr(provider, 'slug', '?')}' on context "
                f"'{getattr(context_cls, 'SLUG', '?')}': {e}"
            )
            continue

        for integration in integrations:
            uuid = integration.uuid
            context_uuids.append(uuid)

            if uuid in all_integrations:
                # Already seen this integration in this package
                continue

            # Compute specification_path relative to package source
            location = getattr(integration, "location", None)
            spec_path = ""
            if location:
                try:
                    spec_path = str(Path(location).resolve().relative_to(
                        Path(package_source_path).resolve()
                    ))
                except ValueError:
                    # location is outside package source; use absolute
                    spec_path = str(location)

            # Compute content hash from api.yaml
            content_hash = ""
            if location:
                api_yaml_path = Path(location) / "api.yaml"
                if api_yaml_path.is_file():
                    content_hash = _sha256_file(api_yaml_path)

            all_integrations[uuid] = {
                "uuid": uuid,
                "slug": integration.slug or "",
                "specification_path": spec_path,
                "name": integration.name,
                "description": integration.description or "",
                "content_hash": content_hash,
            }

    return context_uuids


def _extract_workflows(
    context_cls: type[BeakerContext],
    package_source_path: str,
    all_workflows: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Extract workflows for a context class with stable file-path-based identity.
    Deduplicates by file_path into all_workflows. Returns workflow_refs for this context.
    """
    workflow_refs: list[dict[str, Any]] = []

    # Locate workflows directory, mirroring BeakerContext.discover_workflows:
    # unset -> {class_dir}/workflows; relative -> resolved against class_dir.
    try:
        class_dir = os.path.dirname(inspect.getfile(context_cls))
    except (TypeError, OSError):
        return workflow_refs

    workflow_dir = getattr(context_cls, "workflow_location", None)
    if workflow_dir is None:
        workflows_dir = os.path.join(class_dir, "workflows")
    elif not os.path.isabs(workflow_dir):
        workflows_dir = os.path.normpath(os.path.join(class_dir, workflow_dir))
    else:
        workflows_dir = str(workflow_dir)

    if not os.path.isdir(workflows_dir):
        return workflow_refs

    sort_order = 0
    for workflow_yaml in sorted(Path(workflows_dir).glob("*.yaml")):
        try:
            raw_content = workflow_yaml.read_bytes()
            workflow = Workflow.from_yaml(yaml.safe_load(raw_content))
        except Exception as e:
            logger.warning(f"Failed to parse workflow '{workflow_yaml}': {e}")
            continue

        # Compute file_path relative to package source
        try:
            file_path = str(workflow_yaml.resolve().relative_to(
                Path(package_source_path).resolve()
            ))
        except ValueError:
            file_path = str(workflow_yaml)

        content_hash = hashlib.sha256(raw_content).hexdigest()

        # Add to package-level workflows if not already present
        if file_path not in all_workflows:
            all_workflows[file_path] = {
                "file_path": file_path,
                "content_hash": content_hash,
                "title": workflow.title,
                "human_description": workflow.human_description,
                "agent_description": workflow.agent_description,
                "example_prompt": workflow.example_prompt,
                "category_slug": workflow.category,
                "agent_instructions": workflow.agent_instructions,
                "hidden": workflow.hidden or False,
                "metadata": workflow.metadata or {},
                "stages": [
                    {
                        "name": stage.name,
                        "sort_order": idx,
                        "description": stage.description or [],
                        "metadata": stage.metadata or {},
                    }
                    for idx, stage in enumerate(workflow.stages)
                ],
            }

        # Build ref for this context
        workflow_refs.append({
            "file_path": file_path,
            "is_context_default": workflow.is_context_default or False,
            "sort_order": sort_order,
        })
        sort_order += 1

    return workflow_refs


def _extract_language_slugs(context_cls: type[BeakerContext]) -> list[str]:
    """Extract supported language slugs from a context class."""
    try:
        subkernels = context_cls.available_subkernels()
        return list(subkernels.keys())
    except Exception as e:
        logger.warning(
            f"Failed to get available subkernels for "
            f"'{getattr(context_cls, 'SLUG', '?')}': {e}"
        )
        # Fallback to compatible_subkernels class var
        compatible = getattr(context_cls, "compatible_subkernels", None)
        return list(compatible) if compatible else []


def _build_context_record(
    context_cls: type[BeakerContext],
    slug: str,
    integration_uuids: list[str],
    workflow_refs: list[dict[str, Any]],
    language_slugs: list[str],
) -> dict[str, Any]:
    """Build a ContextRecordDump dict for a single context class."""
    # Look for default_payload.json adjacent to the context class file
    default_payload = "{}"
    try:
        class_file = inspect.getfile(context_cls)
        payload_path = Path(class_file).parent / "default_payload.json"
        if payload_path.is_file():
            default_payload = payload_path.read_text().strip()
    except (TypeError, OSError):
        pass

    return {
        "slug": slug,
        "class_name": context_cls.__name__,
        "module_path": context_cls.__module__,
        "display_name": getattr(context_cls, "FULL_NAME", None),
        "description": (context_cls.__doc__ or "").strip() or None,
        "weight": getattr(context_cls, "WEIGHT", 50),
        "default_payload": default_payload,
        "integration_uuids": integration_uuids,
        "api_key_env_vars": [],  # TODO: No mechanism to enumerate required API keys yet
        "language_slugs": language_slugs,
        "workflow_refs": workflow_refs,
    }


def _sha256_file(path: Path) -> str:
    """Compute SHA256 hex digest of a file's contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dumps_to_json(dumps: list[dict[str, Any]], pretty: bool = True) -> str:
    """Serialize dumps to JSON string."""
    indent = 2 if pretty else None
    return json.dumps(dumps, indent=indent, default=str)
