import inspect
import json
import logging
import os
import re
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Optional, Mapping, cast
from typing_extensions import Self
from uuid import uuid4

import requests
import yaml
from archytas.tool_utils import tool, AgentRef

from beaker_notebook.lib.autodiscovery import find_resource_dirs
from beaker_notebook.lib.integrations.types import (
    Integration,
    Resource,
    SkillExampleResource,
    SkillFileResource,
    SkillInstructionsResource,
    SkillIntegration,
    SkillMetadataResource,
)
from .base import MutableBaseIntegrationProvider

# Subdirectories under a local skill directory that hold progressively-disclosed
# resource files (mirrors the Agent Skills layout). Order is the display order.
# Both "references" and the singular "reference" are recognized because real
# skills (e.g. Anthropic's own) use the singular form.
SKILL_RESOURCE_DIRS = ("references", "reference", "scripts", "assets")
if TYPE_CHECKING:
    from beaker_notebook.lib.agent import BeakerAgent
    from beaker_notebook.lib.context import BeakerContext
    from archytas.chat_history import ChatHistory
    from archytas.models.base import BaseArchytasModel
    from langchain_core.messages import ToolMessage

logger = logging.getLogger(__name__)


async def _summarize_skill_resource(
    message: "ToolMessage",
    chat_history: "ChatHistory",
    agent: "BeakerAgent",
    model: "Optional[BaseArchytasModel]" = None,
) -> None:
    """Elide a loaded skill resource after its react loop completes.

    Keeps the tool result in history as a short pointer so the agent can
    re-invoke the tool to recover the content. Respects the ``persist``
    arg: when True, the content is left intact.
    """
    artifact = getattr(message, "artifact", None) or {}
    tool_name = artifact.get("tool_name")
    if not tool_name:
        return

    _, tool_call = chat_history.get_tool_caller(message.tool_call_id)
    if not tool_call:
        return
    args = tool_call.get("args") or {}

    if args.get("persist"):
        artifact["summarized"] = True
        return

    skill_slug = args.get("skill_slug", "<unknown>")
    relative_path = args.get("relative_path", "<unknown>")
    try:
        if model is not None:
            token_count = await model.get_num_tokens_from_messages([message])
        else:
            token_count = "<unknown>"
    except:
        token_count = "<unknown>"


    message.content = f"""
Resource '{relative_path}' from skill '{skill_slug}' was loaded, but its contents have been elided to save context.
The contents of the resource have been cached and can be retrieved by reloading the resource, such as by
calling `load_skill_resource(skill_slug={skill_slug!r}, relative_path={relative_path!r})` again.
The full resource has a size of approximately {token_count} tokens.
""".strip()
    artifact["summarized"] = True

    tool_fn = agent.tools.get(tool_name)
    provider = getattr(tool_fn, "__self__", None) if tool_fn else None
    if provider is not None:
        try:
            skill = provider._find_skill_by_slug(skill_slug)
        except ValueError:
            return
        session_id = provider._get_session_id(agent)
        provider._loaded.get(session_id, set()).discard((skill.slug, relative_path))


async def _summarize_skill_examples(
    message: "ToolMessage",
    chat_history: "ChatHistory",
    agent: "BeakerAgent",
    model: "Optional[BaseArchytasModel]" = None,
) -> None:
    """Elide loaded skill examples after their react loop completes."""
    artifact = getattr(message, "artifact", None) or {}
    tool_name = artifact.get("tool_name")
    if not tool_name:
        return

    _, tool_call = chat_history.get_tool_caller(message.tool_call_id)
    if not tool_call:
        return
    args = tool_call.get("args") or {}

    skill_slug = args.get("skill_slug", "<unknown>")
    filenames = args.get("filenames") or []

    message.content = f"""
Examples {filenames} from skill '{skill_slug}' were loaded, but their contents have been elided to save context.
The contents of the skills have been cached and can be retrieved by reloading the resource, such as by
calling `load_skill_examples(skill_slug={skill_slug!r}, filenames=[...])` again if you need to re-read any of them.
""".strip()
    artifact["summarized"] = True

    tool_fn = agent.tools.get(tool_name)
    provider: "Optional[SkillIntegrationProvider]" = cast("Optional[SkillIntegrationProvider]", getattr(tool_fn, "__self__", None)) if tool_fn else None
    if provider is not None:
        try:
            skill = provider._find_skill_by_slug(skill_slug)
        except ValueError:
            return
        session_id = provider._get_session_id(agent)
        marks = provider._loaded.get(session_id, set())
        for fn in filenames:
            marks.discard((skill.slug, f"examples/{fn}"))


def parse_skill_md(content: str) -> tuple[dict, str]:
    """Parse SKILL.md content into (frontmatter_dict, markdown_body)."""
    parts = content.split("---", 2)
    if len(parts) < 3:
        raise ValueError("SKILL.md must contain YAML frontmatter delimited by ---")
    frontmatter = yaml.safe_load(parts[1])
    if not isinstance(frontmatter, dict):
        raise ValueError("SKILL.md frontmatter must be a YAML mapping")
    body = parts[2].strip()
    return frontmatter, body


def extract_file_references(body: str) -> list[str]:
    """Extract relative file paths referenced in the markdown body.

    Detects both markdown links [text](path) and backtick-quoted paths
    like `references/some_file.md` or `scripts/run.py`.
    """
    references = []

    # Markdown links: [text](path)
    link_pattern = re.compile(r'\[(?:[^\]]*)\]\(([^)]+)\)')
    for match in link_pattern.finditer(body):
        path = match.group(1)
        # Normalize a leading "./" so a body reference like ./reference/x.md
        # matches the on-disk / enumerated path (reference/x.md) and dedupes
        # rather than appearing as a separate, phantom resource.
        if path.startswith("./"):
            path = path[2:]
        if not path.startswith(("http://", "https://", "#", "mailto:")):
            # Skip examples/ paths — they are handled as SkillExampleResources
            if not path.startswith("examples/") and path != "examples/":
                references.append(path)

    # Backtick-quoted file paths: `some/path.ext`
    # Match paths that contain a / and end with a file extension
    backtick_pattern = re.compile(r'`((?:references|reference|scripts|assets)/[^`]+)`')
    for match in backtick_pattern.finditer(body):
        references.append(match.group(1))

    # Deduplicate preserving order
    return list(dict.fromkeys(references))


def parse_example_md(content: str) -> tuple[str, str]:
    """Extract (title, description) from an example markdown file.

    Expects the format:
        # Title line
        <blank line>
        Description paragraph...
    """
    lines = content.strip().splitlines()
    title = ""
    description = ""
    if lines and lines[0].startswith("# "):
        title = lines[0][2:].strip()
    # Collect the first non-empty paragraph after the title
    desc_lines = []
    in_desc = False
    for line in lines[1:]:
        stripped = line.strip()
        if not in_desc:
            if stripped:
                in_desc = True
                desc_lines.append(stripped)
        else:
            if not stripped or stripped.startswith("#"):
                break
            desc_lines.append(stripped)
    description = " ".join(desc_lines)
    return title, description


class SkillIntegrationProvider(MutableBaseIntegrationProvider):
    """Provides Agent Skills as Beaker integrations with progressive disclosure.

    Skills are discovered from a skills.json config file containing a list of
    local paths and/or remote URLs pointing to SKILL.md files.

    Local skills are editable: their ``SKILL.md`` (name/description/frontmatter
    metadata + instructions body) is written through ``update_integration`` and
    their resource files (under ``references/``/``scripts/``/``assets/`` and
    ``examples/``) through the resource-mutation methods. Remote skills are
    defined by a URL only; their fetched content is read-only.
    """

    provider_type: ClassVar[str] = "agent-skill"
    display_name: ClassVar[str] = "Agent Skills"
    slug: ClassVar[str] = "agent-skill"

    def __init__(self, id: Optional[str] = None, skill_paths: Optional[list[str|os.PathLike]] = None):
        super().__init__(id=id)
        logger.debug(f"Initializing SkillIntegrationProvider {self.display_name} ({self.id})")
        self._skills: list[SkillIntegration] = list(
            self.discover_integrations(paths=skill_paths, corpus=self.id).values()
        )
        self._loaded: dict[str, set[tuple[str, str]]] = {}

    @classmethod
    def _get_skill_search_roots(cls) -> list[Path]:
        """Return base directories to search for skills, ordered from most
        specific (highest precedence on conflicts) to most general.

        Each root is searched for both ``skills.json`` and a ``skills/``
        subdirectory. The conventional locations are:
          - Project-level: ./.agents/, ./.beaker/
          - User-level:    ~/.agents/, ~/.beaker/
          - Data dirs:     entries from find_resource_dirs("data")

        ``.agents`` is listed before ``.beaker`` at each level so that a
        notebook-root ``./.agents/skills.json`` overrides any conflicting
        skills declared elsewhere.
        """
        roots: list[Path] = []
        seen: set[Path] = set()

        def _add(p: Path):
            try:
                resolved = p.resolve()
            except OSError:
                resolved = p
            if resolved in seen or not p.is_dir():
                return
            seen.add(resolved)
            roots.append(p)

        # Project-level (most specific)
        cwd = Path.cwd()
        for name in (".agents", ".beaker"):
            _add(cwd / name)

        # User-level
        home = Path.home()
        for name in (".agents", ".beaker"):
            _add(home / name)

        # Data dirs from autodiscovery
        for data_dir in find_resource_dirs("data"):
            _add(Path(data_dir))

        return roots

    @classmethod
    def from_context(cls, context: "BeakerContext") -> list[Self]:
        # Check for a skills.json file a the same level as the context.py and load it if it exists.
        context_dir_path = Path(inspect.getabsfile(context.__class__)).parent
        integration_paths = cls.discover_integration_paths(root_paths=[context_dir_path])
        if integration_paths:
            # Namespace context-bundled skills under a `context-<slug>` id so the
            # front-end (isContextProvidedIntegration) renders them read-only,
            # mirroring MCPIntegrationProvider.from_context.
            return [cls(id=f"context-{context.slug}", skill_paths=integration_paths)]
        else:
            return []


    @classmethod
    def discover_integration_paths(
        cls, root_paths: Optional[list[str|os.PathLike]] = None
    ) -> list[Path]:
        """Locate ``skills.json`` config files within the given roots.

        Each root directory is checked for a ``skills.json`` manifest; a root
        that points directly at a ``skills.json`` file is returned as-is. When
        ``root_paths`` is ``None`` the conventional skill search roots are used.
        Returns the config file paths in root order; does not read them.

        Note: this locates only ``skills.json`` manifests. Skills installed
        under a root's ``skills/`` convention directory are not config-file
        driven and are handled directly in :meth:`discover_integrations`.
        """
        roots = cls._get_skill_search_roots() if root_paths is None else [Path(p) for p in root_paths]

        config_files: list[Path] = []
        for root in roots:
            if root.is_file() and root.name == "skills.json":
                config_files.append(root)
            elif root.is_dir():
                if root.name == "skills":
                    config_files.append(root)
                else:
                    candidate_file = root / "skills.json"
                    if candidate_file.is_file():
                        config_files.append(candidate_file)
                    candidate_dir = root / "skills"
                    if candidate_dir.is_dir() and any(child.is_dir() for child in candidate_dir.iterdir()):
                        config_files.append(candidate_dir)
        return config_files

    @classmethod
    def discover_integrations(cls, *, paths: Optional[list[str|os.PathLike]] = None, corpus: Optional[str] = None, **kwargs) -> Mapping[str, SkillIntegration]:
        """Discover and load skills from ``skills.json`` files and ``skills/``
        directories under each search root.

        Each root is checked for both a ``skills.json`` manifest and a
        ``skills/`` subdirectory; roots earlier in the list take precedence
        on slug conflicts. ``corpus`` namespaces the built integrations (and
        their deterministic uuids); it is the owning provider's id.
        """
        skills: dict[str, SkillIntegration] = {}
        loaded_slugs: set[str] = set()

        def _load_deduped(source: str, base_path: Optional[str]=None, manifest_path: Optional[str]=None):
            try:
                skill = cls._load_skill(source, base_path=base_path, corpus=corpus, manifest_path=manifest_path)
                if skill.slug in loaded_slugs:
                    logger.debug("Skipping duplicate skill '%s' from %s", skill.name, source)
                else:
                    loaded_slugs.add(skill.slug)
                    skills[skill.uuid] = skill
            except Exception:
                logger.exception("Failed to load skill from source: %s", source)

        # 1) skills.json manifests. Processed before the skills/ scan so a
        #    manifest entry wins on slug conflicts.
        for config_path in cls.discover_integration_paths(paths):
            logger.debug("Found skills.json at %s", config_path)
            if config_path.is_file():
                try:
                    with open(config_path) as f:
                        data = json.load(f)
                except Exception:
                    logger.exception("Failed to read skills.json at %s", config_path)
                    continue
                if not isinstance(data, list):
                    logger.warning("skills.json must be a JSON list, got %s", type(data).__name__)
                    continue
                for source in data:
                    _load_deduped(source, base_path=str(config_path.parent), manifest_path=str(config_path))
            elif config_path.is_dir():
                logger.debug("Scanning skills directory: %s", config_path)
                for skill_md in config_path.glob("*/SKILL.md"):
                    _load_deduped(str(skill_md.parent), base_path=str(config_path))

        return skills

    @classmethod
    def _merge(cls, a: Self, b: Self) -> Self:
        existing_skills = {skill.slug for skill in a._skills}
        for skill in b._skills:
            if skill.slug not in existing_skills:
                a._skills.append(skill)
        return a

    @classmethod
    def _load_skill(cls, source: str, base_path: Optional[str]=None, corpus: Optional[str]=None, manifest_path: Optional[str]=None) -> SkillIntegration:
        """Load a single skill from a local path or remote URL."""
        if source.startswith(("http://", "https://")):
            return cls._load_remote_skill(source, corpus=corpus, manifest_path=manifest_path)
        else:
            # If the source reference is relative, convert it to an absolute path relative to the folder the json file is in.
            if not Path(source).is_absolute() and base_path is not None:
                source = str((Path(base_path) / source).absolute())
            return cls._load_local_skill(source, corpus=corpus)

    @classmethod
    def _load_local_skill(cls, path: str, corpus: Optional[str]=None) -> SkillIntegration:
        """Load a skill from a local directory or SKILL.md path."""
        skill_path = Path(path)
        if skill_path.is_file() and skill_path.name == "SKILL.md":
            skill_md_path = skill_path
            skill_dir = skill_path.parent
        elif skill_path.is_dir():
            skill_md_path = skill_path / "SKILL.md"
            skill_dir = skill_path
        else:
            raise FileNotFoundError(f"Not a valid skill source: {path}")

        if not skill_md_path.is_file():
            raise FileNotFoundError(f"SKILL.md not found at {skill_md_path}")

        content = skill_md_path.read_text(encoding="utf-8")
        frontmatter, body = parse_skill_md(content)

        slug = str(skill_dir.name)

        return cls._build_skill_integration(
            slug=slug,
            frontmatter=frontmatter,
            body=body,
            source_type="local",
            base_path=str(skill_dir),
            corpus=corpus,
        )

    @classmethod
    def _load_remote_skill(cls, url: str, corpus: Optional[str]=None, manifest_path: Optional[str]=None) -> SkillIntegration:
        """Load a skill from a remote URL."""
        if url.rstrip("/").endswith("SKILL.md"):
            skill_url = url
            base_url = url[:url.rstrip("/").rfind("/") + 1]
        else:
            base_url = url.rstrip("/") + "/"
            skill_url = base_url + "SKILL.md"

        response = requests.get(skill_url, timeout=30)
        response.raise_for_status()

        frontmatter, body = parse_skill_md(response.text)

        return cls._build_skill_integration(
            frontmatter=frontmatter,
            body=body,
            source_type="remote",
            base_url=base_url,
            corpus=corpus,
            # Retain where this remote skill was declared, and under what source
            # string, so update_integration can rewrite the manifest entry.
            source_url=url,
            manifest_path=manifest_path,
        )

    @classmethod
    def _build_skill_integration(
        cls,
        frontmatter: dict,
        body: str,
        source_type: str,
        slug: Optional[str] = None,
        base_path: Optional[str] = None,
        base_url: Optional[str] = None,
        corpus: Optional[str] = None,
        source_url: Optional[str] = None,
        manifest_path: Optional[str] = None,
    ) -> SkillIntegration:
        """Build a SkillIntegration with resources from parsed SKILL.md."""
        name = frontmatter["name"]
        description = frontmatter["description"]

        if slug is None:
            slug = Integration.slugify(name)

        skill = SkillIntegration(
            uuid=cls._skill_uuid(slug, corpus),
            name=name,
            slug=slug,
            description=description,
            provider=f"{cls.provider_type}:{cls.slug}",
            source_type=source_type,
            base_path=base_path,
            base_url=base_url,
            corpus=corpus,
        )
        if source_url:
            # Surface the source URL as the integration's url so the editor can
            # display it; also retained in extra_metadata for manifest rewrites.
            skill.url = source_url
            skill.extra_metadata["source_url"] = source_url
        if manifest_path:
            skill.extra_metadata["manifest_path"] = manifest_path

        metadata_resource = SkillMetadataResource(
            integration=skill.uuid,
            skill_name=name,
            skill_slug=skill.slug,
            description=description,
            license=frontmatter.get("license"),
            compatibility=frontmatter.get("compatibility"),
            allowed_tools=frontmatter.get("allowed-tools"),
            skill_metadata=frontmatter.get("metadata") or {},
        )

        instructions_resource = SkillInstructionsResource(
            integration=skill.uuid,
            content=body,
        )

        file_resources = cls._discover_file_resources(skill, body, source_type, base_path)
        example_resources = cls._discover_examples(skill, source_type, base_path, base_url)

        skill.add_resources([metadata_resource, instructions_resource] + file_resources + example_resources)
        return skill

    @classmethod
    def _skill_uuid(cls, slug: str, corpus: Optional[str]) -> str:
        """Deterministic uuid for a skill: ``agent-skill:<corpus>:<slug>``.

        Stable across reloads within a provider's lifetime (``corpus`` is the
        provider id), so an edit -> save -> re-fetch round-trip keeps the same
        identity, mirroring the MCP provider's scheme.
        """
        return f"{cls.slug}:{corpus}:{slug}"

    # Resource ids are left as auto-generated uuid4s (see Resource.__post_init__)
    # rather than derived from the skill uuid / path: the resource routes carry
    # the id as a URL path segment (regex `[\w\d-]+`), so it must not contain
    # ':', '.', or '/'. The front-end always uses the ids from the freshly
    # fetched integration, so stability across reloads is not required.

    @classmethod
    def _discover_file_resources(
        cls,
        skill: SkillIntegration,
        body: str,
        source_type: str,
        base_path: Optional[str] = None,
    ) -> list[SkillFileResource]:
        """Build the skill's ``skill_file`` resources.

        For a local skill the on-disk contents of the resource dirs
        (``references``/``reference``/``scripts``/``assets``) are the sole source
        of truth. Body references are deliberately NOT used for local skills:
        they would create phantom or duplicate resources — a referenced-but-
        absent path, a different spelling (``./x`` vs ``x``), or a copy of a file
        that is also uploaded separately. For a remote skill (which cannot be
        scanned) the body references are the only signal available.
        """
        seen: dict[str, SkillFileResource] = {}

        def _add(relative_path: str):
            if relative_path in seen:
                return
            seen[relative_path] = SkillFileResource(
                integration=skill.uuid,
                name=Path(relative_path).name,
                relative_path=relative_path,
            )

        if source_type == "local":
            if base_path:
                root = Path(base_path)
                for subdir in SKILL_RESOURCE_DIRS:
                    dir_path = root / subdir
                    if not dir_path.is_dir():
                        continue
                    for file_path in sorted(dir_path.rglob("*")):
                        if file_path.is_file():
                            _add(str(file_path.relative_to(root)))
            # A local skill with no base_path (e.g. an upload preview) has no
            # files to enumerate yet; the client provides them on save.
        else:
            for ref_path in extract_file_references(body):
                _add(ref_path)

        return list(seen.values())

    @classmethod
    def _discover_examples(
        cls,
        skill: SkillIntegration,
        source_type: str,
        base_path: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> list[SkillExampleResource]:
        """Discover example files from the skill's examples/ directory.

        For local skills, scans the examples/ subdirectory. For remote skills,
        examples must be declared in the frontmatter (not yet implemented).
        Only reads the first few lines of each file to extract title and description.
        """
        resources = []
        if source_type == "local" and base_path:
            examples_dir = Path(base_path) / "examples"
            if examples_dir.is_dir():
                for example_path in sorted(examples_dir.glob("*.md")):
                    try:
                        content = example_path.read_text(encoding="utf-8")
                        title, description = parse_example_md(content)
                        resources.append(SkillExampleResource(
                            integration=skill.uuid,
                            filename=example_path.name,
                            title=title or example_path.stem,
                            description=description,
                            content=None,  # Loaded on demand (tier 3)
                        ))
                    except Exception:
                        logger.exception("Failed to parse example: %s", example_path)
        return resources

    # --- Abstract method implementations ---

    def list_integrations(self) -> list[Integration]:
        return list(self._skills)

    def get_integration(self, integration_id: str) -> SkillIntegration:
        for skill in self._skills:
            if skill.uuid == integration_id:
                return skill
        raise KeyError(f"Skill integration not found: {integration_id}")

    def list_resources(self, integration_id: str, resource_type: Optional[str] = None) -> list[Resource]:
        skill = self.get_integration(integration_id)
        resources = list(skill.resources.values())
        if resource_type:
            resources = [r for r in resources if r.resource_type == resource_type]
        return resources

    def get_resource(self, integration_id: str, resource_id: str) -> Resource:
        skill = self.get_integration(integration_id)
        if resource_id not in skill.resources:
            raise KeyError(f"Resource not found: {resource_id}")
        resource = skill.resources[resource_id]
        # Auto-load content on demand for file and example resources
        if isinstance(resource, SkillFileResource) and resource.content is None:
            resource.content = self._fetch_file_content(skill, resource.relative_path)
        elif isinstance(resource, SkillExampleResource) and resource.content is None:
            resource.content = self._fetch_file_content(skill, f"examples/{resource.filename}")
        return resource

    # --- Mutation: write-location resolution -----------------------------

    @classmethod
    def _candidate_write_roots(cls) -> list[Path]:
        """Ordered base dirs a user's skills may be written to, most preferred
        first. Mirrors the discovery search roots but keeps locations that do
        not yet exist so a first-run install still has somewhere to land.
        """
        roots: list[Path] = []
        cwd = Path.cwd()
        for name in (".agents", ".beaker"):
            roots.append(cwd / name)
        home = Path.home()
        for name in (".agents", ".beaker"):
            roots.append(home / name)
        for data_dir in find_resource_dirs("data"):
            roots.append(Path(data_dir))
        return roots

    @classmethod
    def _resolve_writable_base(cls) -> Path:
        """Pick a base dir for new skills/manifests.

        Uses the first candidate root that already exists and is writable; if
        none exist, the first candidate we can create. Raises if nothing is
        writable.
        """
        candidates = cls._candidate_write_roots()
        for root in candidates:
            if root.is_dir() and os.access(root, os.W_OK):
                return root
        for root in candidates:
            try:
                root.mkdir(parents=True, exist_ok=True)
                return root
            except OSError:
                continue
        raise OSError("No writable location available to store skills.")

    def _resolve_writable_manifest(self) -> Path:
        """Resolve a ``skills.json`` to record remote-skill URLs in.

        Prefers a manifest this provider already reads from and can write to, so
        a user's remote skills stay collected together; otherwise scaffolds one
        under the first writable base.
        """
        for skill in self._skills:
            manifest_path = skill.extra_metadata.get("manifest_path")
            if manifest_path and Path(manifest_path).is_file() and os.access(manifest_path, os.W_OK):
                return Path(manifest_path)
        manifest = self._resolve_writable_base() / "skills.json"
        if not manifest.exists():
            manifest.write_text("[]\n", encoding="utf-8")
        return manifest

    @staticmethod
    def _read_manifest(path: Path) -> list:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return data if isinstance(data, list) else []

    @classmethod
    def _write_manifest(cls, path: Path, data: list) -> None:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def _manifest_entry_matches(entry: Any, url: str) -> bool:
        return entry == url or (isinstance(entry, dict) and entry.get("source") == url)

    # --- Mutation: SKILL.md serialization --------------------------------

    @staticmethod
    def _frontmatter_from_payload(payload: dict, defaults: Optional[dict] = None) -> dict:
        """Assemble ordered SKILL.md frontmatter from an editor payload.

        Only ``name``/``description`` are required; optional keys are omitted
        when empty so the written file stays clean. ``defaults`` (an existing
        skill's values) backs fields the payload omits on update.
        """
        defaults = defaults or {}
        fm: dict[str, Any] = {
            "name": payload.get("name") or defaults.get("name"),
            "description": payload.get("description")
                if payload.get("description") is not None else defaults.get("description"),
        }
        license_val = payload.get("license", defaults.get("license"))
        if license_val:
            fm["license"] = license_val
        compatibility = payload.get("compatibility", defaults.get("compatibility"))
        if compatibility:
            fm["compatibility"] = compatibility
        allowed_tools = payload.get("allowed_tools", defaults.get("allowed_tools"))
        if allowed_tools:
            fm["allowed-tools"] = allowed_tools
        metadata = payload.get("skill_metadata", defaults.get("skill_metadata"))
        if metadata:
            fm["metadata"] = metadata
        return fm

    @staticmethod
    def _render_skill_md(frontmatter: dict, body: str) -> str:
        clean = {k: v for k, v in frontmatter.items() if v not in (None, "", {}, [])}
        yaml_text = yaml.safe_dump(clean, sort_keys=False, default_flow_style=False).strip()
        return f"---\n{yaml_text}\n---\n\n{(body or '').strip()}\n"

    def _existing_frontmatter_defaults(self, skill: SkillIntegration) -> dict:
        """Current frontmatter-relevant values for a skill, from its metadata
        resource, used to back fields an update payload does not include.
        """
        metadata = next(
            (r for r in skill.resources.values() if isinstance(r, SkillMetadataResource)),
            None,
        )
        return {
            "name": skill.name,
            "description": skill.description,
            "license": getattr(metadata, "license", None),
            "compatibility": getattr(metadata, "compatibility", None),
            "allowed_tools": getattr(metadata, "allowed_tools", None),
            "skill_metadata": getattr(metadata, "skill_metadata", None),
        }

    def _existing_body(self, skill: SkillIntegration) -> str:
        instructions = next(
            (r for r in skill.resources.values() if isinstance(r, SkillInstructionsResource)),
            None,
        )
        return instructions.content if instructions else ""

    def _replace_skill(self, uuid: str, new_skill: SkillIntegration) -> None:
        for i, skill in enumerate(self._skills):
            if skill.uuid == uuid:
                self._skills[i] = new_skill
                return
        self._skills.append(new_skill)

    # --- Mutation: integrations ------------------------------------------

    def add_integration(self, **payload) -> Integration:
        # Preview: build and return the (unsaved) skill so the editor can
        # populate its form before the user commits. Nothing is written to disk
        # or added to the catalog. A remote preview fetches the SKILL.md from a
        # URL; a local/upload preview parses SKILL.md text supplied directly.
        if payload.get("preview"):
            return self._preview_integration(**payload)
        if payload.get("source_type") == "remote":
            return self._add_remote_integration(**payload)
        return self._add_local_integration(**payload)

    def _preview_integration(self, **payload) -> SkillIntegration:
        if payload.get("source_type") == "remote":
            url = (payload.get("url") or "").strip()
            if not url:
                raise ValueError("Cannot preview remote skill: a URL is required.")
            return self._load_remote_skill(url, corpus=self.id)
        content = payload.get("content")
        if not content:
            raise ValueError("Cannot preview skill: SKILL.md content is required.")
        frontmatter, body = parse_skill_md(content)
        # base_path is intentionally omitted: the client enumerates the uploaded
        # skill's resource files itself and uploads them on save. This preview
        # only supplies name/description/metadata/instructions for the form.
        return self._build_skill_integration(
            frontmatter=frontmatter,
            body=body,
            source_type="local",
            corpus=self.id,
        )

    def _add_local_integration(self, **payload) -> SkillIntegration:
        name = payload.get("name")
        if not name:
            raise ValueError("Cannot add skill: a name is required.")
        slug = Integration.slugify(name)
        if any(skill.slug == slug for skill in self._skills):
            raise ValueError(f"A skill named '{name}' (slug '{slug}') already exists.")
        skill_dir = self._resolve_writable_base() / "skills" / slug
        if skill_dir.exists():
            raise ValueError(f"Skill directory already exists: {skill_dir}")
        skill_dir.mkdir(parents=True)
        frontmatter = self._frontmatter_from_payload(payload)
        (skill_dir / "SKILL.md").write_text(
            self._render_skill_md(frontmatter, payload.get("instructions") or ""),
            encoding="utf-8",
        )
        skill = self._load_local_skill(str(skill_dir), corpus=self.id)
        self._skills.append(skill)
        return skill

    def _add_remote_integration(self, **payload) -> SkillIntegration:
        url = (payload.get("url") or "").strip()
        if not url:
            raise ValueError("Cannot add remote skill: a URL is required.")
        manifest = self._resolve_writable_manifest()
        data = self._read_manifest(manifest)
        if not any(self._manifest_entry_matches(entry, url) for entry in data):
            data.append(url)
            self._write_manifest(manifest, data)
        try:
            skill = self._load_remote_skill(url, corpus=self.id, manifest_path=str(manifest))
        except Exception:
            # Roll back the manifest entry so a failed fetch leaves no dangling row.
            self._remove_manifest_url(manifest, url)
            raise
        if any(existing.slug == skill.slug for existing in self._skills):
            self._remove_manifest_url(manifest, url)
            raise ValueError(f"A skill with slug '{skill.slug}' already exists.")
        self._skills.append(skill)
        return skill

    def update_integration(self, integration_id: str, **payload) -> Integration:
        skill = self.get_integration(integration_id)
        if skill.source_type == "remote":
            return self._update_remote_integration(skill, **payload)
        return self._update_local_integration(skill, **payload)

    def _update_local_integration(self, skill: SkillIntegration, **payload) -> SkillIntegration:
        if not skill.base_path:
            raise ValueError(f"Skill '{skill.slug}' has no local path to write to.")
        # The directory name (and thus slug/uuid) is fixed at creation; only the
        # SKILL.md content changes here.
        defaults = self._existing_frontmatter_defaults(skill)
        frontmatter = self._frontmatter_from_payload(payload, defaults=defaults)
        body = payload.get("instructions")
        if body is None:
            body = self._existing_body(skill)
        (Path(skill.base_path) / "SKILL.md").write_text(
            self._render_skill_md(frontmatter, body), encoding="utf-8",
        )
        refreshed = self._load_local_skill(skill.base_path, corpus=skill.corpus)
        self._replace_skill(skill.uuid, refreshed)
        return refreshed

    def _update_remote_integration(self, skill: SkillIntegration, **payload) -> SkillIntegration:
        new_url = (payload.get("url") or "").strip()
        if not new_url:
            raise ValueError("A URL is required for a remote skill.")
        old_url = skill.extra_metadata.get("source_url")
        manifest = skill.extra_metadata.get("manifest_path")
        if not manifest:
            raise ValueError("Cannot locate the manifest for this remote skill.")
        manifest_path = Path(manifest)
        if new_url != old_url:
            data = self._read_manifest(manifest_path)
            for i, entry in enumerate(data):
                if entry == old_url:
                    data[i] = new_url
                elif isinstance(entry, dict) and entry.get("source") == old_url:
                    entry["source"] = new_url
            self._write_manifest(manifest_path, data)
        refreshed = self._load_remote_skill(new_url, corpus=skill.corpus, manifest_path=manifest)
        self._replace_skill(skill.uuid, refreshed)
        return refreshed

    def remove_integration(self, integration_id: str, **payload) -> None:
        skill = self.get_integration(integration_id)
        if skill.source_type == "remote":
            manifest = skill.extra_metadata.get("manifest_path")
            url = skill.extra_metadata.get("source_url")
            if manifest and url:
                self._remove_manifest_url(Path(manifest), url)
        elif skill.base_path and Path(skill.base_path).is_dir():
            shutil.rmtree(skill.base_path)
        self._skills = [existing for existing in self._skills if existing.uuid != integration_id]

    def _remove_manifest_url(self, manifest: Path, url: str) -> None:
        data = self._read_manifest(manifest)
        remaining = [entry for entry in data if not self._manifest_entry_matches(entry, url)]
        if len(remaining) != len(data):
            self._write_manifest(manifest, remaining)

    # --- Mutation: resources (local skills only) -------------------------

    @staticmethod
    def _require_local_editable(skill: SkillIntegration) -> None:
        if skill.source_type != "local" or not skill.base_path:
            raise ValueError(f"Skill '{skill.slug}' is not a local skill and its resources cannot be edited.")

    @staticmethod
    def _validate_resource_path(relative_path: str) -> None:
        path = Path(relative_path)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"Invalid resource path: {relative_path}")
        if not path.parts or path.parts[0] not in SKILL_RESOURCE_DIRS:
            raise ValueError(
                f"Resource path must be under one of {SKILL_RESOURCE_DIRS}: {relative_path}"
            )

    def _write_skill_file(self, skill: SkillIntegration, relative_path: str, content: str) -> None:
        base = Path(skill.base_path).resolve()
        target = (base / relative_path).resolve()
        if target != base and base not in target.parents:
            raise ValueError(f"Refusing to write outside the skill directory: {relative_path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def _delete_skill_file(self, skill: SkillIntegration, relative_path: str) -> None:
        target = Path(skill.base_path) / relative_path
        if target.is_file():
            target.unlink()

    def add_resource(self, integration_id: str, **payload) -> Resource:
        skill = self.get_integration(integration_id)
        self._require_local_editable(skill)
        resource_type = payload.get("resource_type")
        content = payload.get("content") or ""
        if resource_type == "skill_file":
            relative_path = payload.get("relative_path")
            if not relative_path:
                raise ValueError("A skill_file resource requires a relative_path.")
            self._validate_resource_path(relative_path)
            self._write_skill_file(skill, relative_path, content)
            resource: Resource = SkillFileResource(
                integration=skill.uuid,
                name=payload.get("name") or Path(relative_path).name,
                relative_path=relative_path,
                content=content,
            )
        elif resource_type == "skill_example":
            filename = payload.get("filename")
            if not filename:
                raise ValueError("A skill_example resource requires a filename.")
            self._write_skill_file(skill, f"examples/{filename}", content)
            parsed_title, parsed_description = parse_example_md(content)
            resource = SkillExampleResource(
                integration=skill.uuid,
                filename=filename,
                title=payload.get("title") or parsed_title or Path(filename).stem,
                description=payload.get("description") or parsed_description,
                content=content,
            )
        else:
            raise ValueError(
                f"Cannot add a resource of type '{resource_type}' to a skill. "
                "Editable resource types are 'skill_file' and 'skill_example'; "
                "the instructions body and metadata are edited via the integration itself."
            )
        skill.resources[resource.resource_id] = resource
        return resource

    def update_resource(self, integration_id: str, resource_id: str, **payload) -> Resource:
        skill = self.get_integration(integration_id)
        self._require_local_editable(skill)
        resource = skill.resources.get(resource_id)
        if resource is None:
            raise KeyError(f"Resource not found: {resource_id}")
        content = payload.get("content")
        if isinstance(resource, SkillFileResource):
            if content is not None:
                self._write_skill_file(skill, resource.relative_path, content)
                resource.content = content
        elif isinstance(resource, SkillExampleResource):
            if content is not None:
                self._write_skill_file(skill, f"examples/{resource.filename}", content)
                resource.content = content
                parsed_title, parsed_description = parse_example_md(content)
                resource.title = payload.get("title") or parsed_title or resource.title
                resource.description = payload.get("description") or parsed_description or resource.description
        else:
            raise ValueError(
                "Only 'skill_file' and 'skill_example' resources are editable; "
                "instructions and metadata are edited via the integration itself."
            )
        return resource

    def remove_resource(self, integration_id: str, resource_id: str, **payload) -> None:
        skill = self.get_integration(integration_id)
        self._require_local_editable(skill)
        resource = skill.resources.get(resource_id)
        if resource is None:
            return
        if isinstance(resource, SkillFileResource):
            self._delete_skill_file(skill, resource.relative_path)
        elif isinstance(resource, SkillExampleResource):
            self._delete_skill_file(skill, f"examples/{resource.filename}")
        else:
            raise ValueError("Only 'skill_file' and 'skill_example' resources can be removed.")
        skill.resources.pop(resource_id, None)

    # --- Prompt (Tier 1: metadata only, as YAML) ---

    @property
    def prompt(self) -> str:
        if not self._skills:
            return ""
        skills: list[dict[str, Any]] = []
        for skill in self._skills:
            metadata = next(
                (r for r in skill.resources.values() if isinstance(r, SkillMetadataResource)),
                None,
            )
            if not metadata:
                continue
            entry: dict[str, Any] = {
                "name": metadata.skill_name,
                "slug": metadata.skill_slug,
                "description": metadata.description,
            }
            entry["compatibility"] = metadata.compatibility or None
            file_resources = [
                r for r in skill.resources.values() if isinstance(r, SkillFileResource)
            ]
            entry["available_resources"] = [r.relative_path for r in file_resources]
            example_resources = [
                r for r in skill.resources.values() if isinstance(r, SkillExampleResource)
            ]
            entry["has_code_examples"] = bool(len(example_resources))
            skills.append(entry)
        data = {
            "usage": [
                "Use load_skill_instructions(skill_slug) to load a skill's full "
                "instructions before using it.",
                "Use load_skill_resource(skill_slug, relative_path) to load a "
                "skill's reference files or scripts.",
                "Use load_skill_examples(skill_slug, filenames) to load code "
                "examples for a skill. Available examples are listed when instructions are loaded.",
            ],
            "provider": self.display_name,
            "skills": skills,
        }
        yaml_string = yaml.safe_dump(data, sort_keys=False, default_flow_style=False).rstrip("\n")
        return f"""
```yaml
{yaml_string}
```
        """.strip()

    # --- Deduplication ---

    def _is_loaded(self, session_id: str, skill_slug: str, resource_key: str) -> bool:
        return (skill_slug, resource_key) in self._loaded.get(session_id, set())

    def _mark_loaded(self, session_id: str, skill_slug: str, resource_key: str):
        if session_id not in self._loaded:
            self._loaded[session_id] = set()
        self._loaded[session_id].add((skill_slug, resource_key))

    def clear_session(self, session_id: str):
        """Clear deduplication state for a session (called on session reset)."""
        self._loaded.pop(session_id, None)

    # --- Helpers ---

    def _find_skill_by_slug(self, skill_slug: str) -> SkillIntegration:
        for skill in self._skills:
            if skill.slug == skill_slug:
                return skill
        raise ValueError(f"Skill not found: {skill_slug}")

    def _get_session_id(self, agent: "BeakerAgent") -> str:
        # TODO: Make sure this is valid
        return agent.context.subkernel.kernel_id

    def _fetch_file_content(self, skill: SkillIntegration, relative_path: str) -> str:
        """Fetch file content from local filesystem or remote URL."""
        if skill.source_type == "local" and skill.base_path:
            file_path = Path(skill.base_path) / relative_path
            if not file_path.is_file():
                raise FileNotFoundError(f"Skill file not found: {file_path}")
            return file_path.read_text(encoding="utf-8")
        elif skill.source_type == "remote" and skill.base_url:
            file_url = skill.base_url + relative_path
            response = requests.get(file_url, timeout=30)
            response.raise_for_status()
            return response.text
        raise ValueError(f"Cannot fetch file for skill '{skill.slug}': no base path or URL")

    # --- Tools (Tier 2 and 3) ---

    @tool(internal=True)
    async def load_skill_instructions(self, skill_slug: str, agent: AgentRef) -> str:
        """Load the full instructions for a skill. Call this before using a skill.

        The instructions will be added to the context and will be retained for the remainder of the session.

        Args:
            skill_slug: The slug of the skill to load instructions for.

        Returns:
            str: The skill's full markdown instructions, or a status message if already loaded.
        """
        session_id = self._get_session_id(agent)

        if self._is_loaded(session_id, skill_slug, "instructions"):
            return f"Skill instructions for '{skill_slug}' have already been loaded in this session."

        skill = self._find_skill_by_slug(skill_slug)
        instructions = next(
            (r for r in skill.resources.values() if isinstance(r, SkillInstructionsResource)),
            None,
        )
        if not instructions:
            return f"No instructions found for skill '{skill_slug}'."

        self._mark_loaded(session_id, skill.slug, "instructions")

        result = instructions.content

        # Append code example listing if any exist
        examples = [
            r for r in skill.resources.values() if isinstance(r, SkillExampleResource)
        ]
        if examples:
            result += "\n\n## Available Code Examples\n"
            for ex in examples:
                result += f"\n- **{ex.filename}**: {ex.title}"
                if ex.description:
                    result += f"\n  {ex.description}"
            result += (
                "\n\nUse `load_skill_examples(skill_slug, filenames)` to load "
                "one or more code examples before writing code."
            )

        return result

    @tool(summarizer=_summarize_skill_resource, internal=True)
    async def load_skill_resource(self, skill_slug: str, relative_path: str, agent: AgentRef, persist: bool = False) -> str:
        """Load a resource file (script, reference doc, or asset) from a skill.

        Unless persisted, the full contents of the resource will be included in the context until the end of the current ReAct loop.
        However, the contents are cached and can be reloaded by calling this tool again if you need it in the future.
        If you need to cite or provide a reference to this file, you can simply refer to it via skill name and relative path.
        Users can access the resource via the user interface if needed.

        Args:
            skill_slug: The name or slug of the skill.
            relative_path: The relative path of the resource file (e.g. "references/use_cases.md").
            persist: Set to true if the resource should be persisted in the message history or false to summarize to prevent context bloat (default: False)

        Returns:
            str: The file content, or a status message if already loaded.
        """
        session_id = self._get_session_id(agent)

        if self._is_loaded(session_id, skill_slug, relative_path):
            return (
                f"Resource '{relative_path}' for skill '{skill_slug}' "
                "has already been loaded in this session."
            )

        skill = self._find_skill_by_slug(skill_slug)
        file_resource = next(
            (r for r in skill.resources.values()
             if isinstance(r, SkillFileResource) and r.relative_path == relative_path),
            None,
        )
        if not file_resource:
            return f"Resource '{relative_path}' not found for skill '{skill_slug}'."

        # Load content on demand
        if file_resource.content is None:
            file_resource.content = self._fetch_file_content(skill, relative_path)

        self._mark_loaded(session_id, skill.name, relative_path)
        return file_resource.content

    @tool(summarizer=_summarize_skill_examples, internal=True)
    async def load_skill_examples(self, skill_slug: str, filenames: list[str], agent: AgentRef) -> str:
        """Load one or more code examples for a skill. Call this after loading instructions and before writing code, to see working usage patterns.

        The full contents of the example files will be included in the context until the end of the current ReAct loop.
        The examples are cached and can be reloaded by calling this tool again if you need it in the future.
        If you need to cite or provide a reference to these examples, you can simply refer to it by skill name and filenames.
        Users can access the examples via the user interface if needed.

        Args:
            skill_slug: The name or slug of the skill.
            filenames: List of example filenames to load (e.g. ["airport_intelligence.md", "flight_tracking.md"]).

        Returns:
            str: The concatenated example contents, separated by headers.
        """
        session_id = self._get_session_id(agent)
        skill = self._find_skill_by_slug(skill_slug)

        all_examples = {
            r.filename: r
            for r in skill.resources.values()
            if isinstance(r, SkillExampleResource)
        }

        parts = []
        already_loaded = []
        not_found = []

        for filename in filenames:
            if self._is_loaded(session_id, skill.name, f"examples/{filename}"):
                already_loaded.append(filename)
                continue

            example = all_examples.get(filename)
            if not example:
                not_found.append(filename)
                continue

            # Load content on demand
            if example.content is None:
                example.content = self._fetch_file_content(skill, f"examples/{filename}")

            self._mark_loaded(session_id, skill.name, f"examples/{filename}")
            parts.append(f"# Example: {example.title}\n\n{example.content}")

        result_parts = []
        if parts:
            result_parts.append("\n\n---\n\n".join(parts))
        if already_loaded:
            result_parts.append(f"Already loaded in this session: {', '.join(already_loaded)}")
        if not_found:
            available = ", ".join(sorted(all_examples.keys()))
            result_parts.append(
                f"Not found: {', '.join(not_found)}. "
                f"Available examples: {available}"
            )

        return "\n\n".join(result_parts) if result_parts else f"No examples found for skill '{skill_slug}'."
