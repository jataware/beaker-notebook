import inspect
import json
import logging
import os
import re
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
from .base import BaseIntegrationProvider
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


#: Directory, relative to the skill root, whose contents are examples rather
#: than plain reference files. Referenced paths under it become
#: SkillExampleResources; see `_build_skill_integration`.
EXAMPLES_DIR = "examples/"


def extract_file_references(body: str) -> list[str]:
    """Extract relative file paths referenced in the markdown body.

    Detects both markdown links [text](path) and backtick-quoted paths
    like `references/some_file.md` or `scripts/run.py`.

    Paths under ``examples/`` are included. The caller decides what a path
    becomes -- `_build_skill_integration` routes them to SkillExampleResources
    rather than SkillFileResources -- so this stays a single, uniform pass over
    the body. A bare ``examples/`` directory link names no file and is dropped.
    """
    references = []

    # Markdown links: [text](path)
    link_pattern = re.compile(r'\[(?:[^\]]*)\]\(([^)]+)\)')
    for match in link_pattern.finditer(body):
        path = match.group(1)
        if path.startswith(("http://", "https://", "#", "mailto:")):
            continue
        # A link to the directory itself, not to a file in it.
        if path.rstrip("/") == EXAMPLES_DIR.rstrip("/"):
            continue
        references.append(path)

    # Backtick-quoted file paths: `some/path.ext`
    # Match paths that contain a / and end with a file extension
    backtick_pattern = re.compile(r'`((?:references|scripts|assets|examples)/[^`]+)`')
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


class SkillIntegrationProvider(BaseIntegrationProvider):
    """Provides Agent Skills as Beaker integrations with progressive disclosure.

    Skills are discovered from a skills.json config file containing a list of
    local paths and/or remote URLs pointing to SKILL.md files.
    """

    provider_type: ClassVar[str] = "agent-skill"
    display_name: ClassVar[str] = "Agent Skills"
    slug: ClassVar[str] = "agent-skill"
    mutable: ClassVar[bool] = False

    def __init__(self, id: Optional[str] = None, skill_paths: Optional[list[str|os.PathLike]] = None):
        super().__init__(id=id)
        logger.debug(f"Initializing SkillIntegrationProvider {self.display_name} ({self.id})")
        self._skills: list[SkillIntegration] = list(self.discover_integrations(paths=skill_paths).values())
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
            return [cls(skill_paths=integration_paths)]
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
    def discover_integrations(cls, *, paths: Optional[list[str|os.PathLike]] = None, **kwargs) -> Mapping[str, SkillIntegration]:
        """Discover and load skills from ``skills.json`` files and ``skills/``
        directories under each search root.

        Each root is checked for both a ``skills.json`` manifest and a
        ``skills/`` subdirectory; roots earlier in the list take precedence
        on slug conflicts.
        """
        skills: dict[str, SkillIntegration] = {}
        loaded_slugs: set[str] = set()

        def _load_deduped(source: str, base_path: Optional[str]=None):
            try:
                skill = cls._load_skill(source, base_path=base_path)
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
                    _load_deduped(source, base_path=str(config_path.parent))
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
    def _load_skill(cls, source: str, base_path: Optional[str]=None) -> SkillIntegration:
        """Load a single skill from a local path or remote URL."""
        if source.startswith(("http://", "https://")):
            return cls._load_remote_skill(source)
        else:
            # If the source reference is relative, convert it to an absolute path relative to the folder the json file is in.
            if not Path(source).is_absolute() and base_path is not None:
                source = str((Path(base_path) / source).absolute())
            return cls._load_local_skill(source)

    @classmethod
    def _load_local_skill(cls, path: str) -> SkillIntegration:
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
        )

    @classmethod
    def _load_remote_skill(cls, url: str) -> SkillIntegration:
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
    ) -> SkillIntegration:
        """Build a SkillIntegration with resources from parsed SKILL.md."""
        name = frontmatter["name"]
        description = frontmatter["description"]

        skill = SkillIntegration(
            name=name,
            slug=cast(str, slug),
            description=description,
            provider=f"{cls.provider_type}:{cls.slug}",
            source_type=source_type,
            base_path=base_path,
            base_url=base_url,
        )

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

        # One pass over the body; the prefix decides which kind of resource a
        # referenced path becomes. Examples have their own tier and their own
        # loading tool, so they must not also appear as plain files.
        file_resources = []
        referenced_examples = []
        for ref_path in extract_file_references(body):
            if ref_path.startswith(EXAMPLES_DIR):
                referenced_examples.append(ref_path)
            else:
                file_resources.append(SkillFileResource(
                    integration=skill.uuid,
                    name=Path(ref_path).name,
                    relative_path=ref_path,
                ))

        example_resources = cls._discover_examples(
            skill, source_type, base_path, base_url, referenced=referenced_examples
        )

        skill.add_resources([metadata_resource, instructions_resource] + file_resources + example_resources)
        return skill

    @classmethod
    def _discover_examples(
        cls,
        skill: SkillIntegration,
        source_type: str,
        base_path: Optional[str] = None,
        base_url: Optional[str] = None,
        referenced: "Optional[list[str]]" = None,
    ) -> list[SkillExampleResource]:
        """Discover a skill's examples, from the directory and from the body.

        Two sources, in precedence order:

        1. **Local directory scan.** Reads enough of each ``examples/*.md`` file
           to pull out a title and description. Only possible for local skills.
        2. **Paths referenced in SKILL.md**, passed in as ``referenced``. This is
           the only source available to a remote skill, where the directory
           cannot be listed over HTTP, and it also picks up local examples the
           ``*.md`` glob misses -- a skill shipping ``examples/*.py`` was
           previously invisible whether it was local or remote.

        The scan wins on conflict because it carries a real parsed title and
        description; a referenced path yields only its filename. That costs
        little, because the agent must call ``load_skill_instructions`` -- which
        returns the whole body, author's example listing included -- before it
        can ask for an example by name.

        Content is never fetched here; it stays tier 3, loaded on demand.
        """
        resources = []
        seen: set[str] = set()

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
                        seen.add(example_path.name)
                    except Exception:
                        logger.exception("Failed to parse example: %s", example_path)

        for relative_path in referenced or []:
            # Keep the path below examples/ as the filename so nested examples
            # round-trip through load_skill_examples and _fetch_file_content.
            filename = relative_path[len(EXAMPLES_DIR):]
            if not filename or filename in seen:
                continue
            seen.add(filename)
            resources.append(SkillExampleResource(
                integration=skill.uuid,
                filename=filename,
                title=filename,
                description="",
                content=None,  # Loaded on demand (tier 3)
            ))

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
                result += f"\n- **{ex.filename}**"
                # An example discovered from a reference in the body has no
                # title beyond its own filename; printing it twice reads as a
                # bug and spends tokens saying nothing.
                if ex.title and ex.title != ex.filename:
                    result += f": {ex.title}"
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
