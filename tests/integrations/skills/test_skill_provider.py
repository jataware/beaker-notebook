"""Tests for the SkillIntegrationProvider and related utilities."""

import json
import os
import textwrap
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from beaker_kernel.lib.integrations.skill import (
    SkillIntegrationProvider,
    parse_skill_md,
    parse_example_md,
    extract_file_references,
)
from beaker_kernel.lib.types import (
    SkillExampleResource,
    SkillFileResource,
    SkillInstructionsResource,
    SkillIntegration,
    SkillMetadataResource,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MINIMAL_SKILL_MD = textwrap.dedent("""\
    ---
    name: minimal-skill
    description: A minimal test skill.
    ---

    # Minimal Skill

    Just some instructions.
""")

FULL_SKILL_MD = textwrap.dedent("""\
    ---
    name: full-skill
    description: A full-featured test skill with all frontmatter fields.
    license: MIT
    compatibility: Requires Python 3.10+
    allowed-tools: Bash(git:*) Read
    metadata:
      author: test-org
      version: "2.0"
    ---

    # Full Skill

    Refer to [the guide](references/guide.md) and `references/patterns.md` for details.

    Also see `scripts/run.py` for the main entrypoint.

    External link: [docs](https://example.com/docs) should be ignored.
""")


@pytest.fixture
def skill_dir(tmp_path: Path) -> Path:
    """Create a local skill directory with a SKILL.md and a reference file."""
    skill = tmp_path / "full-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text(FULL_SKILL_MD)

    refs = skill / "references"
    refs.mkdir()
    (refs / "guide.md").write_text("# Guide\n\nThis is the guide content.")
    (refs / "patterns.md").write_text("# Patterns\n\nSome patterns here.")

    scripts = skill / "scripts"
    scripts.mkdir()
    (scripts / "run.py").write_text("print('hello')")

    examples = skill / "examples"
    examples.mkdir()
    (examples / "basic_usage.md").write_text(textwrap.dedent("""\
        # Basic usage of the full skill

        Demonstrates the simplest way to use this skill with default settings.

        ## Example

        ```python
        print("hello world")
        ```
    """))
    (examples / "advanced_usage.md").write_text(textwrap.dedent("""\
        # Advanced usage with chained API calls

        Shows how to chain multiple API calls together for complex workflows.

        ## Example

        ```python
        result = chain(call_a(), call_b())
        ```
    """))

    return skill


@pytest.fixture
def skills_data_dir(tmp_path: Path, skill_dir: Path) -> Path:
    """Create a data directory with skills.json and a skills/ subdirectory."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # skills.json pointing to the full-skill directory
    skills_json = data_dir / "skills.json"
    skills_json.write_text(json.dumps([str(skill_dir)]))

    # Also put a minimal skill in the skills/ subdirectory
    skills_subdir = data_dir / "skills" / "minimal-skill"
    skills_subdir.mkdir(parents=True)
    (skills_subdir / "SKILL.md").write_text(MINIMAL_SKILL_MD)

    return data_dir


def _make_provider(data_dirs: list[str], extra_scan_dirs: list[Path] = None) -> SkillIntegrationProvider:
    """Create a provider with patched resource dirs to avoid loading from the real filesystem."""
    scan_dirs = list(extra_scan_dirs or [])
    # Include {data_dir}/skills for each data_dir, matching the real _get_skill_scan_dirs behavior
    for d in data_dirs:
        p = Path(d) / "skills"
        if p.is_dir():
            scan_dirs.append(p)

    with patch(
        "beaker_kernel.lib.integrations.skill.find_resource_dirs",
        return_value=data_dirs,
    ), patch.object(
        SkillIntegrationProvider,
        "_get_skill_scan_dirs",
        return_value=scan_dirs,
    ):
        return SkillIntegrationProvider()


# ---------------------------------------------------------------------------
# parse_skill_md
# ---------------------------------------------------------------------------

class TestParseSkillMd:
    def test_minimal(self):
        fm, body = parse_skill_md(MINIMAL_SKILL_MD)
        assert fm["name"] == "minimal-skill"
        assert fm["description"] == "A minimal test skill."
        assert "# Minimal Skill" in body

    def test_full_frontmatter(self):
        fm, body = parse_skill_md(FULL_SKILL_MD)
        assert fm["name"] == "full-skill"
        assert fm["license"] == "MIT"
        assert fm["compatibility"] == "Requires Python 3.10+"
        assert fm["allowed-tools"] == "Bash(git:*) Read"
        assert fm["metadata"]["author"] == "test-org"
        assert fm["metadata"]["version"] == "2.0"

    def test_missing_frontmatter_raises(self):
        with pytest.raises(ValueError, match="YAML frontmatter"):
            parse_skill_md("No frontmatter here")

    def test_non_dict_frontmatter_raises(self):
        with pytest.raises(ValueError, match="YAML mapping"):
            parse_skill_md("---\n- just a list\n---\nBody")


# ---------------------------------------------------------------------------
# extract_file_references
# ---------------------------------------------------------------------------

class TestExtractFileReferences:
    def test_markdown_links(self):
        body = "See [guide](references/guide.md) and [script](scripts/run.py)."
        refs = extract_file_references(body)
        assert "references/guide.md" in refs
        assert "scripts/run.py" in refs

    def test_backtick_paths(self):
        body = "Use `references/patterns.md` and `scripts/extract.sh` and `assets/template.json`."
        refs = extract_file_references(body)
        assert "references/patterns.md" in refs
        assert "scripts/extract.sh" in refs
        assert "assets/template.json" in refs

    def test_external_urls_ignored(self):
        body = "See [docs](https://example.com) and [anchor](#section)."
        refs = extract_file_references(body)
        assert len(refs) == 0

    def test_deduplication(self):
        body = (
            "See `references/guide.md` here and also `references/guide.md` there. "
            "And [link](references/guide.md) too."
        )
        refs = extract_file_references(body)
        assert refs.count("references/guide.md") == 1

    def test_mixed_references(self):
        refs = extract_file_references(FULL_SKILL_MD.split("---", 2)[2])
        assert "references/guide.md" in refs
        assert "references/patterns.md" in refs
        assert "scripts/run.py" in refs

    def test_examples_paths_excluded(self):
        body = (
            "See [examples/](examples/) for working examples.\n"
            "Also see [examples/basic.md](examples/basic.md) for a quick start.\n"
            "And [the guide](references/guide.md) for docs."
        )
        refs = extract_file_references(body)
        assert "examples/" not in refs
        assert "examples/basic.md" not in refs
        assert "references/guide.md" in refs


# ---------------------------------------------------------------------------
# SkillIntegrationProvider — local loading
# ---------------------------------------------------------------------------

class TestLocalSkillLoading:
    def test_load_from_skills_json(self, skills_data_dir: Path):
        provider = _make_provider([str(skills_data_dir)])
        names = [s.name for s in provider.list_integrations()]
        assert "full-skill" in names

    def test_load_from_skills_directory(self, skills_data_dir: Path):
        provider = _make_provider([str(skills_data_dir)])
        names = [s.name for s in provider.list_integrations()]
        assert "minimal-skill" in names

    def test_both_sources_loaded(self, skills_data_dir: Path):
        provider = _make_provider([str(skills_data_dir)])
        assert len(provider.list_integrations()) == 2

    def test_skill_integration_fields(self, skills_data_dir: Path):
        provider = _make_provider([str(skills_data_dir)])
        skill = provider._find_skill_by_name("full-skill")
        assert isinstance(skill, SkillIntegration)
        assert skill.datatype == "skill"
        assert skill.source_type == "local"
        assert skill.base_path is not None
        assert skill.provider == "agent-skill:agent-skill"

    def test_load_from_skill_md_path(self, skill_dir: Path):
        """Can load by pointing directly at a SKILL.md file."""
        skill = SkillIntegrationProvider._load_local_skill(str(skill_dir / "SKILL.md"))
        assert skill.name == "full-skill"

    def test_missing_skill_md_raises(self, tmp_path: Path):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        with pytest.raises(FileNotFoundError):
            SkillIntegrationProvider._load_local_skill(str(empty_dir))


# ---------------------------------------------------------------------------
# Discovery paths
# ---------------------------------------------------------------------------

class TestDiscoveryPaths:
    def test_skills_from_extra_scan_dirs(self, tmp_path: Path):
        """Skills discovered from extra scan dirs (e.g. ~/.agents/skills/)."""
        agents_skills = tmp_path / "agents_skills"
        agents_skills.mkdir()
        skill = agents_skills / "agent-skill-one"
        skill.mkdir()
        (skill / "SKILL.md").write_text(MINIMAL_SKILL_MD)

        provider = _make_provider([], extra_scan_dirs=[agents_skills])
        names = [s.name for s in provider.list_integrations()]
        assert "minimal-skill" in names

    def test_project_level_overrides_user_level(self, tmp_path: Path):
        """Project-level skills take precedence over user-level (scanned first)."""
        project_skills = tmp_path / "project"
        project_skills.mkdir()
        skill_proj = project_skills / "my-skill"
        skill_proj.mkdir()
        (skill_proj / "SKILL.md").write_text(textwrap.dedent("""\
            ---
            name: my-skill
            description: Project version.
            ---
            # Project version
        """))

        user_skills = tmp_path / "user"
        user_skills.mkdir()
        skill_user = user_skills / "my-skill"
        skill_user.mkdir()
        (skill_user / "SKILL.md").write_text(textwrap.dedent("""\
            ---
            name: my-skill
            description: User version.
            ---
            # User version
        """))

        # Project dir listed first = higher precedence
        provider = _make_provider([], extra_scan_dirs=[project_skills, user_skills])
        skills = provider.list_integrations()
        assert len(skills) == 1
        assert skills[0].description == "Project version."

    def test_skills_json_takes_precedence_over_scan_dirs(self, tmp_path: Path):
        """Skills loaded from skills.json take precedence over directory scans."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        # Create skill via skills.json
        json_skill_dir = tmp_path / "json-skill"
        json_skill_dir.mkdir()
        (json_skill_dir / "SKILL.md").write_text(textwrap.dedent("""\
            ---
            name: shared-name
            description: From skills.json.
            ---
            # JSON version
        """))
        (data_dir / "skills.json").write_text(json.dumps([str(json_skill_dir)]))

        # Same skill name in a scan dir
        scan_skills = tmp_path / "scan"
        scan_skills.mkdir()
        scan_skill = scan_skills / "shared-name"
        scan_skill.mkdir()
        (scan_skill / "SKILL.md").write_text(textwrap.dedent("""\
            ---
            name: shared-name
            description: From scan dir.
            ---
            # Scan version
        """))

        provider = _make_provider([str(data_dir)], extra_scan_dirs=[scan_skills])
        skills = provider.list_integrations()
        assert len(skills) == 1
        assert skills[0].description == "From skills.json."

    def test_get_skill_scan_dirs_returns_existing_only(self, tmp_path: Path, monkeypatch):
        """_get_skill_scan_dirs only returns directories that actually exist."""
        monkeypatch.chdir(tmp_path)

        # Create only .beaker/skills at project level
        beaker_skills = tmp_path / ".beaker" / "skills"
        beaker_skills.mkdir(parents=True)
        # .agents/skills does NOT exist

        with patch(
            "beaker_kernel.lib.integrations.skill.find_resource_dirs",
            return_value=[],
        ):
            provider = SkillIntegrationProvider.__new__(SkillIntegrationProvider)
            dirs = provider._get_skill_scan_dirs()

        dir_strs = [str(d) for d in dirs]
        assert str(beaker_skills) in dir_strs
        assert str(tmp_path / ".agents" / "skills") not in dir_strs


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

class TestDeduplication:
    def test_duplicate_skill_loaded_once(self, skill_dir: Path, tmp_path: Path):
        """If skills.json and skills/ both reference the same skill, only one is loaded."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        # skills.json references the skill
        (data_dir / "skills.json").write_text(json.dumps([str(skill_dir)]))

        # Also put a copy in skills/ directory
        skills_subdir = data_dir / "skills" / "full-skill"
        skills_subdir.mkdir(parents=True)
        (skills_subdir / "SKILL.md").write_text(FULL_SKILL_MD)

        provider = _make_provider([str(data_dir)])
        names = [s.name for s in provider.list_integrations()]
        assert names.count("full-skill") == 1


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

class TestResources:
    def test_metadata_resource(self, skills_data_dir: Path):
        provider = _make_provider([str(skills_data_dir)])
        skill = provider._find_skill_by_name("full-skill")
        metadata_resources = provider.list_resources(skill.uuid, resource_type="skill_metadata")
        assert len(metadata_resources) == 1
        meta = metadata_resources[0]
        assert isinstance(meta, SkillMetadataResource)
        assert meta.skill_name == "full-skill"
        assert meta.license == "MIT"
        assert meta.compatibility == "Requires Python 3.10+"
        assert meta.allowed_tools == "Bash(git:*) Read"
        assert meta.skill_metadata["author"] == "test-org"

    def test_instructions_resource(self, skills_data_dir: Path):
        provider = _make_provider([str(skills_data_dir)])
        skill = provider._find_skill_by_name("full-skill")
        instr_resources = provider.list_resources(skill.uuid, resource_type="skill_instructions")
        assert len(instr_resources) == 1
        instr = instr_resources[0]
        assert isinstance(instr, SkillInstructionsResource)
        assert "# Full Skill" in instr.content

    def test_file_resources_enumerated(self, skills_data_dir: Path):
        provider = _make_provider([str(skills_data_dir)])
        skill = provider._find_skill_by_name("full-skill")
        file_resources = provider.list_resources(skill.uuid, resource_type="skill_file")
        paths = {r.relative_path for r in file_resources}
        assert "references/guide.md" in paths
        assert "references/patterns.md" in paths
        assert "scripts/run.py" in paths

    def test_file_resources_content_not_loaded(self, skills_data_dir: Path):
        """File resource content should be None until explicitly fetched."""
        provider = _make_provider([str(skills_data_dir)])
        skill = provider._find_skill_by_name("full-skill")
        file_resources = provider.list_resources(skill.uuid, resource_type="skill_file")
        for r in file_resources:
            assert r.content is None

    def test_get_resource_by_id(self, skills_data_dir: Path):
        provider = _make_provider([str(skills_data_dir)])
        skill = provider._find_skill_by_name("full-skill")
        all_resources = provider.list_resources(skill.uuid)
        for resource in all_resources:
            fetched = provider.get_resource(skill.uuid, resource.resource_id)
            assert fetched.resource_id == resource.resource_id

    def test_get_resource_missing_raises(self, skills_data_dir: Path):
        provider = _make_provider([str(skills_data_dir)])
        skill = provider._find_skill_by_name("full-skill")
        with pytest.raises(KeyError):
            provider.get_resource(skill.uuid, "nonexistent-id")


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

class TestPrompt:
    def test_prompt_includes_skill_metadata(self, skills_data_dir: Path):
        provider = _make_provider([str(skills_data_dir)])
        prompt = provider.prompt
        assert "full-skill" in prompt
        assert "minimal-skill" in prompt

    def test_prompt_includes_location(self, skills_data_dir: Path):
        provider = _make_provider([str(skills_data_dir)])
        skill = provider._find_skill_by_name("full-skill")
        assert f"Location: {skill.base_path}" in provider.prompt

    def test_prompt_includes_compatibility(self, skills_data_dir: Path):
        provider = _make_provider([str(skills_data_dir)])
        assert "Requires Python 3.10+" in provider.prompt

    def test_prompt_includes_tool_instructions(self, skills_data_dir: Path):
        provider = _make_provider([str(skills_data_dir)])
        assert "load_skill_instructions" in provider.prompt
        assert "load_skill_resource" in provider.prompt
        assert "load_skill_examples" in provider.prompt

    def test_prompt_includes_code_example_count(self, skills_data_dir: Path):
        provider = _make_provider([str(skills_data_dir)])
        assert "Code examples: 2" in provider.prompt

    def test_prompt_lists_available_resources(self, skills_data_dir: Path):
        provider = _make_provider([str(skills_data_dir)])
        assert "references/guide.md" in provider.prompt

    def test_prompt_empty_when_no_skills(self):
        provider = _make_provider([])
        assert provider.prompt == ""


# ---------------------------------------------------------------------------
# On-demand file fetching
# ---------------------------------------------------------------------------

class TestFileFetching:
    def test_fetch_local_file(self, skills_data_dir: Path):
        provider = _make_provider([str(skills_data_dir)])
        skill = provider._find_skill_by_name("full-skill")
        content = provider._fetch_file_content(skill, "references/guide.md")
        assert "# Guide" in content
        assert "guide content" in content

    def test_fetch_local_file_missing_raises(self, skills_data_dir: Path):
        provider = _make_provider([str(skills_data_dir)])
        skill = provider._find_skill_by_name("full-skill")
        with pytest.raises(FileNotFoundError):
            provider._fetch_file_content(skill, "references/nonexistent.md")

    def test_fetch_remote_file(self):
        provider = _make_provider([])

        mock_response = MagicMock()
        mock_response.text = "# Remote Content"
        mock_response.raise_for_status = MagicMock()

        skill = SkillIntegration(
            name="remote-skill",
            description="test",
            provider="agent-skill:agent-skill",
            source_type="remote",
            base_url="https://example.com/skills/my-skill/",
        )

        with patch("beaker_kernel.lib.integrations.skill.requests.get", return_value=mock_response) as mock_get:
            content = provider._fetch_file_content(skill, "references/guide.md")
            mock_get.assert_called_once_with(
                "https://example.com/skills/my-skill/references/guide.md",
                timeout=30,
            )
            assert content == "# Remote Content"


# ---------------------------------------------------------------------------
# Session deduplication
# ---------------------------------------------------------------------------

class TestSessionDedup:
    def test_mark_and_check(self):
        provider = _make_provider([])
        assert not provider._is_loaded("sess1", "my-skill", "instructions")
        provider._mark_loaded("sess1", "my-skill", "instructions")
        assert provider._is_loaded("sess1", "my-skill", "instructions")

    def test_sessions_isolated(self):
        provider = _make_provider([])
        provider._mark_loaded("sess1", "my-skill", "instructions")
        assert not provider._is_loaded("sess2", "my-skill", "instructions")

    def test_clear_session(self):
        provider = _make_provider([])
        provider._mark_loaded("sess1", "my-skill", "instructions")
        provider._mark_loaded("sess1", "my-skill", "references/guide.md")
        provider.clear_session("sess1")
        assert not provider._is_loaded("sess1", "my-skill", "instructions")
        assert not provider._is_loaded("sess1", "my-skill", "references/guide.md")

    def test_clear_session_preserves_other_sessions(self):
        provider = _make_provider([])
        provider._mark_loaded("sess1", "my-skill", "instructions")
        provider._mark_loaded("sess2", "my-skill", "instructions")
        provider.clear_session("sess1")
        assert provider._is_loaded("sess2", "my-skill", "instructions")

    def test_clear_nonexistent_session_is_noop(self):
        provider = _make_provider([])
        provider.clear_session("nonexistent")  # should not raise


# ---------------------------------------------------------------------------
# Remote URL resolution
# ---------------------------------------------------------------------------

class TestRemoteUrlResolution:
    def test_url_ending_with_skill_md(self):
        mock_response = MagicMock()
        mock_response.text = MINIMAL_SKILL_MD
        mock_response.raise_for_status = MagicMock()

        with patch("beaker_kernel.lib.integrations.skill.requests.get", return_value=mock_response) as mock_get:
            skill = SkillIntegrationProvider._load_remote_skill("https://example.com/repo/main/SKILL.md")
            mock_get.assert_called_once_with("https://example.com/repo/main/SKILL.md", timeout=30)

        assert skill.name == "minimal-skill"
        assert skill.base_url == "https://example.com/repo/main/"

    def test_url_not_ending_with_skill_md(self):
        mock_response = MagicMock()
        mock_response.text = MINIMAL_SKILL_MD
        mock_response.raise_for_status = MagicMock()

        with patch("beaker_kernel.lib.integrations.skill.requests.get", return_value=mock_response) as mock_get:
            skill = SkillIntegrationProvider._load_remote_skill("https://example.com/repo/main")
            mock_get.assert_called_once_with("https://example.com/repo/main/SKILL.md", timeout=30)

        assert skill.base_url == "https://example.com/repo/main/"

    def test_url_with_trailing_slash(self):
        mock_response = MagicMock()
        mock_response.text = MINIMAL_SKILL_MD
        mock_response.raise_for_status = MagicMock()

        with patch("beaker_kernel.lib.integrations.skill.requests.get", return_value=mock_response) as mock_get:
            SkillIntegrationProvider._load_remote_skill("https://example.com/repo/main/")
            mock_get.assert_called_once_with("https://example.com/repo/main/SKILL.md", timeout=30)


# ---------------------------------------------------------------------------
# parse_example_md
# ---------------------------------------------------------------------------

class TestParseExampleMd:
    def test_basic_parsing(self):
        content = "# My Title\n\nThis is the description paragraph.\n\n## Example\n\n```python\nprint('hi')\n```"
        title, description = parse_example_md(content)
        assert title == "My Title"
        assert description == "This is the description paragraph."

    def test_multiline_description(self):
        content = "# Title\n\nFirst line of description\nsecond line continues.\n\n## Example"
        title, description = parse_example_md(content)
        assert title == "Title"
        assert description == "First line of description second line continues."

    def test_no_title(self):
        content = "Just some text\n\nMore text"
        title, description = parse_example_md(content)
        assert title == ""
        # First line is consumed as lines[0] (not a title), description starts from lines[1:]
        assert description == "More text"

    def test_empty_content(self):
        title, description = parse_example_md("")
        assert title == ""
        assert description == ""

    def test_title_only(self):
        title, description = parse_example_md("# Just a title")
        assert title == "Just a title"
        assert description == ""


# ---------------------------------------------------------------------------
# Code examples discovery and resources
# ---------------------------------------------------------------------------

class TestCodeExamples:
    def test_examples_discovered(self, skills_data_dir: Path):
        provider = _make_provider([str(skills_data_dir)])
        skill = provider._find_skill_by_name("full-skill")
        examples = [
            r for r in skill.resources.values()
            if isinstance(r, SkillExampleResource)
        ]
        assert len(examples) == 2
        filenames = {e.filename for e in examples}
        assert filenames == {"advanced_usage.md", "basic_usage.md"}

    def test_example_titles_parsed(self, skills_data_dir: Path):
        provider = _make_provider([str(skills_data_dir)])
        skill = provider._find_skill_by_name("full-skill")
        examples = {
            r.filename: r for r in skill.resources.values()
            if isinstance(r, SkillExampleResource)
        }
        assert examples["basic_usage.md"].title == "Basic usage of the full skill"
        assert examples["advanced_usage.md"].title == "Advanced usage with chained API calls"

    def test_example_descriptions_parsed(self, skills_data_dir: Path):
        provider = _make_provider([str(skills_data_dir)])
        skill = provider._find_skill_by_name("full-skill")
        examples = {
            r.filename: r for r in skill.resources.values()
            if isinstance(r, SkillExampleResource)
        }
        assert "simplest way" in examples["basic_usage.md"].description
        assert "chain multiple" in examples["advanced_usage.md"].description.lower()

    def test_example_content_not_loaded_at_discovery(self, skills_data_dir: Path):
        provider = _make_provider([str(skills_data_dir)])
        skill = provider._find_skill_by_name("full-skill")
        examples = [
            r for r in skill.resources.values()
            if isinstance(r, SkillExampleResource)
        ]
        for ex in examples:
            assert ex.content is None

    def test_example_content_loaded_via_get_resource(self, skills_data_dir: Path):
        provider = _make_provider([str(skills_data_dir)])
        skill = provider._find_skill_by_name("full-skill")
        example = next(
            r for r in skill.resources.values()
            if isinstance(r, SkillExampleResource) and r.filename == "basic_usage.md"
        )
        fetched = provider.get_resource(skill.uuid, example.resource_id)
        assert fetched.content is not None
        assert 'print("hello world")' in fetched.content

    def test_no_examples_dir_is_fine(self, tmp_path: Path):
        """Skills without an examples/ directory should load without errors."""
        skills_dir = tmp_path / "skills"
        skill = skills_dir / "no-examples-skill"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(MINIMAL_SKILL_MD)
        provider = _make_provider([], extra_scan_dirs=[skills_dir])
        loaded_skill = provider._find_skill_by_name("minimal-skill")
        examples = [
            r for r in loaded_skill.resources.values()
            if isinstance(r, SkillExampleResource)
        ]
        assert len(examples) == 0

    def test_fetch_example_content(self, skills_data_dir: Path):
        provider = _make_provider([str(skills_data_dir)])
        skill = provider._find_skill_by_name("full-skill")
        content = provider._fetch_file_content(skill, "examples/basic_usage.md")
        assert "hello world" in content
