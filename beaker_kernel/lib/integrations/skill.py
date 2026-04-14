import json
import logging
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Optional

import requests
import yaml
from archytas.tool_utils import tool, AgentRef

from ..autodiscovery import find_resource_dirs
from ..types import (
    Integration,
    Resource,
    SkillFileResource,
    SkillInstructionsResource,
    SkillIntegration,
    SkillMetadataResource,
)
from .base import BaseIntegrationProvider
if TYPE_CHECKING:
    from beaker_kernel.lib.agent import BeakerAgent

logger = logging.getLogger(__name__)


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
        if not path.startswith(("http://", "https://", "#", "mailto:")):
            references.append(path)

    # Backtick-quoted file paths: `some/path.ext`
    # Match paths that contain a / and end with a file extension
    backtick_pattern = re.compile(r'`((?:references|scripts|assets)/[^`]+)`')
    for match in backtick_pattern.finditer(body):
        references.append(match.group(1))

    # Deduplicate preserving order
    return list(dict.fromkeys(references))


class SkillIntegrationProvider(BaseIntegrationProvider):
    """Provides Agent Skills as Beaker integrations with progressive disclosure.

    Skills are discovered from a skills.json config file containing a list of
    local paths and/or remote URLs pointing to SKILL.md files.
    """

    provider_type: ClassVar[str] = "agent-skill"
    slug: ClassVar[str] = "agent-skill"
    mutable: ClassVar[bool] = False

    def __init__(self, display_name: str = "Agent Skills"):
        super().__init__(display_name)
        logger.warning(f"Initializing SkillIntegrationProvider {display_name}")
        self._skills: list[SkillIntegration] = list(self.discover_integrations().values())
        self._loaded: dict[str, set[tuple[str, str]]] = {}

    @classmethod
    def _get_skill_scan_dirs(cls) -> list[Path]:
        """Return skill directories to scan, ordered from most specific (project)
        to most general (user/system).

        Follows the Agent Skills convention:
          - Project-level: ./.beaker/skills/, ./.agents/skills/
          - User-level:    ~/.beaker/skills/, ~/.agents/skills/
          - Data dirs:     {data_dir}/skills/ (from find_resource_dirs)
        """
        dirs: list[Path] = []

        # Project-level (most specific)
        for name in (".beaker/skills", ".agents/skills"):
            p = Path.cwd() / name
            if p.is_dir():
                dirs.append(p)

        # User-level
        home = Path.home()
        for name in (".beaker/skills", ".agents/skills"):
            p = home / name
            if p.is_dir():
                dirs.append(p)

        # Data dirs from autodiscovery (general → specific, but we process
        # them after the more specific project/user dirs above)
        for data_dir in find_resource_dirs("data"):
            p = Path(data_dir) / "skills"
            if p.is_dir():
                dirs.append(p)

        return dirs

    @classmethod
    def discover_integrations(cls) -> dict[str, SkillIntegration]:
        """Discover and load skills from skills.json, standard skill directories,
        and the cross-client .agents/skills/ convention."""
        skills: dict[str, SkillIntegration] = {}
        loaded_names: set[str] = set()

        def _load_deduped(source: str):
            try:
                skill = cls._load_skill(source)
                if skill.name in loaded_names:
                    logger.debug("Skipping duplicate skill '%s' from %s", skill.name, source)
                else:
                    loaded_names.add(skill.name)
                    skills[skill.uuid] = skill
            except Exception:
                logger.exception("Failed to load skill from source: %s", source)

        # Load from skills.json in data dirs
        for data_dir in find_resource_dirs("data"):
            config_path = Path(data_dir) / "skills.json"
            if config_path.is_file():
                logger.debug("Found skills.json at %s", config_path)
                try:
                    with open(config_path) as f:
                        data = json.load(f)
                    if not isinstance(data, list):
                        logger.warning("skills.json must be a JSON list, got %s", type(data).__name__)
                    else:
                        for source in data:
                            _load_deduped(source)
                except Exception:
                    logger.exception("Failed to read skills.json at %s", config_path)

        # Scan all skill directories for SKILL.md files
        for skills_dir in cls._get_skill_scan_dirs():
            logger.debug("Scanning skills directory: %s", skills_dir)
            for skill_md in skills_dir.glob("*/SKILL.md"):
                _load_deduped(str(skill_md.parent))

        return skills

    @classmethod
    def _load_skill(cls, source: str) -> SkillIntegration:
        """Load a single skill from a local path or remote URL."""
        if source.startswith(("http://", "https://")):
            return cls._load_remote_skill(source)
        else:
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

        return cls._build_skill_integration(
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
        base_path: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> SkillIntegration:
        """Build a SkillIntegration with resources from parsed SKILL.md."""
        name = frontmatter["name"]
        description = frontmatter["description"]

        skill = SkillIntegration(
            name=name,
            description=description,
            provider=f"agent-skill:{cls.slug}",
            source_type=source_type,
            base_path=base_path,
            base_url=base_url,
        )

        metadata_resource = SkillMetadataResource(
            integration=skill.uuid,
            skill_name=name,
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

        file_resources = []
        for ref_path in extract_file_references(body):
            file_resources.append(SkillFileResource(
                integration=skill.uuid,
                name=Path(ref_path).name,
                relative_path=ref_path,
            ))

        skill.add_resources([metadata_resource, instructions_resource] + file_resources)
        return skill

    # --- Abstract method implementations ---

    def list_integrations(self) -> list[Integration]:
        return list(self._skills)

    def get_integration(self, integration_id: str) -> Integration:
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
        # Auto-load content on demand for file resources
        if isinstance(resource, SkillFileResource) and resource.content is None:
            resource.content = self._fetch_file_content(skill, resource.relative_path)
        return resource

    # --- Prompt (Tier 1: metadata only) ---

    @property
    def prompt(self) -> str:
        if not self._skills:
            return ""
        parts = [f"Skills available via the {self.display_name} provider:\n"]
        for skill in self._skills:
            metadata = next(
                (r for r in skill.resources.values() if isinstance(r, SkillMetadataResource)),
                None,
            )
            if not metadata:
                continue
            parts.append(f"Skill: {metadata.skill_name}")
            parts.append(f"  Description: {metadata.description}")
            if metadata.compatibility:
                parts.append(f"  Compatibility: {metadata.compatibility}")
            file_resources = [
                r for r in skill.resources.values() if isinstance(r, SkillFileResource)
            ]
            if file_resources:
                paths = ", ".join(r.relative_path for r in file_resources)
                parts.append(f"  Available resources: {paths}")
            parts.append("")
        parts.append(
            "Use `load_skill_instructions(skill_name)` to load a skill's full "
            "instructions before using it."
        )
        parts.append(
            "Use `load_skill_resource(skill_name, relative_path)` to load a "
            "skill's reference files or scripts."
        )
        return "\n".join(parts)

    # --- Deduplication ---

    def _is_loaded(self, session_id: str, skill_name: str, resource_key: str) -> bool:
        return (skill_name, resource_key) in self._loaded.get(session_id, set())

    def _mark_loaded(self, session_id: str, skill_name: str, resource_key: str):
        if session_id not in self._loaded:
            self._loaded[session_id] = set()
        self._loaded[session_id].add((skill_name, resource_key))

    def clear_session(self, session_id: str):
        """Clear deduplication state for a session (called on session reset)."""
        self._loaded.pop(session_id, None)

    # --- Helpers ---

    def _find_skill_by_name(self, skill_name: str) -> SkillIntegration:
        for skill in self._skills:
            if skill.name == skill_name or skill.slug == skill_name:
                return skill
        raise ValueError(f"Skill not found: {skill_name}")

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
        raise ValueError(f"Cannot fetch file for skill '{skill.name}': no base path or URL")

    # --- Tools (Tier 2 and 3) ---

    @tool
    async def load_skill_instructions(self, skill_name: str, agent: AgentRef) -> str:
        """Load the full instructions for a skill. Call this before using a skill.

        Args:
            skill_name: The name or slug of the skill to load instructions for.

        Returns:
            str: The skill's full markdown instructions, or a status message if already loaded.
        """
        session_id = self._get_session_id(agent)

        if self._is_loaded(session_id, skill_name, "instructions"):
            return f"Skill instructions for '{skill_name}' have already been loaded in this session."

        skill = self._find_skill_by_name(skill_name)
        instructions = next(
            (r for r in skill.resources.values() if isinstance(r, SkillInstructionsResource)),
            None,
        )
        if not instructions:
            return f"No instructions found for skill '{skill_name}'."

        self._mark_loaded(session_id, skill.name, "instructions")
        return instructions.content

    @tool
    async def load_skill_resource(self, skill_name: str, relative_path: str, agent: AgentRef, persist: bool = False) -> str:
        """Load a resource file (script, reference doc, or asset) from a skill.

        Args:
            skill_name: The name or slug of the skill.
            relative_path: The relative path of the resource file (e.g. "references/use_cases.md").
            persist: Set to true if the resource should be persisted in the message history or false to summarize to prevent context bloat (default: False)

        Returns:
            str: The file content, or a status message if already loaded.
        """
        session_id = self._get_session_id(agent)

        if self._is_loaded(session_id, skill_name, relative_path):
            return (
                f"Resource '{relative_path}' for skill '{skill_name}' "
                "has already been loaded in this session."
            )

        skill = self._find_skill_by_name(skill_name)
        file_resource = next(
            (r for r in skill.resources.values()
             if isinstance(r, SkillFileResource) and r.relative_path == relative_path),
            None,
        )
        if not file_resource:
            return f"Resource '{relative_path}' not found for skill '{skill_name}'."

        # Load content on demand
        if file_resource.content is None:
            file_resource.content = self._fetch_file_content(skill, relative_path)

        self._mark_loaded(session_id, skill.name, relative_path)
        return file_resource.content
