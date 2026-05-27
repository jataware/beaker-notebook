"""Tests for the @tool methods on SkillIntegrationProvider."""

import json
import textwrap
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from beaker_notebook.lib.integrations.skill import SkillIntegrationProvider


SKILL_MD = textwrap.dedent("""\
    ---
    name: my-skill
    description: A test skill.
    ---

    # My Skill

    See `references/guide.md`.
""")


@pytest.fixture
def skill_dir(tmp_path: Path) -> Path:
    skill = tmp_path / "my-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text(SKILL_MD)
    refs = skill / "references"
    refs.mkdir()
    (refs / "guide.md").write_text("# Guide content")
    examples = skill / "examples"
    examples.mkdir()
    (examples / "basic.md").write_text(textwrap.dedent("""\
        # Basic example

        A description.

        ## Example
        ```python
        x = 1
        ```
    """))
    (examples / "advanced.md").write_text(textwrap.dedent("""\
        # Advanced example

        Another description.

        ## Example
        ```python
        x = 2
        ```
    """))
    return skill


@pytest.fixture
def provider(tmp_path: Path, skill_dir: Path) -> SkillIntegrationProvider:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "skills.json").write_text(json.dumps([str(skill_dir)]))
    with patch(
        "beaker_notebook.lib.integrations.skill.find_resource_dirs",
        return_value=[],
    ), patch.object(
        SkillIntegrationProvider, "_get_skill_search_roots", return_value=[data_dir],
    ):
        return SkillIntegrationProvider()


def _agent_ref(session_id: str = "kernel-1"):
    return SimpleNamespace(context=SimpleNamespace(subkernel=SimpleNamespace(kernel_id=session_id)))


# --- load_skill_instructions ----------------------------------------------


async def test_load_skill_instructions_returns_body(provider):
    result = await SkillIntegrationProvider.load_skill_instructions(
        provider, skill_slug="my-skill", agent=_agent_ref(),
    )
    assert "# My Skill" in result
    # Examples section should be appended (skill has 2 examples).
    assert "Available Code Examples" in result
    assert "basic.md" in result


async def test_load_skill_instructions_dedupes_per_session(provider):
    agent = _agent_ref("session-A")
    await SkillIntegrationProvider.load_skill_instructions(provider, skill_slug="my-skill", agent=agent)
    second = await SkillIntegrationProvider.load_skill_instructions(provider, skill_slug="my-skill", agent=agent)
    assert "already been loaded" in second


async def test_load_skill_instructions_unknown_slug_raises(provider):
    with pytest.raises(ValueError, match="Skill not found"):
        await SkillIntegrationProvider.load_skill_instructions(
            provider, skill_slug="nope", agent=_agent_ref(),
        )


# --- load_skill_resource ---------------------------------------------------


async def test_load_skill_resource_returns_file_content(provider):
    result = await SkillIntegrationProvider.load_skill_resource(
        provider, skill_slug="my-skill", relative_path="references/guide.md", agent=_agent_ref(),
    )
    assert "Guide content" in result


async def test_load_skill_resource_dedupes_per_session(provider):
    agent = _agent_ref("session-B")
    first = await SkillIntegrationProvider.load_skill_resource(
        provider, skill_slug="my-skill", relative_path="references/guide.md", agent=agent,
    )
    second = await SkillIntegrationProvider.load_skill_resource(
        provider, skill_slug="my-skill", relative_path="references/guide.md", agent=agent,
    )
    assert "Guide content" in first
    assert "already been loaded" in second


async def test_load_skill_resource_missing_path_returns_message(provider):
    result = await SkillIntegrationProvider.load_skill_resource(
        provider, skill_slug="my-skill", relative_path="references/missing.md", agent=_agent_ref(),
    )
    assert "not found" in result.lower()


# --- load_skill_examples --------------------------------------------------


async def test_load_skill_examples_loads_files(provider):
    result = await SkillIntegrationProvider.load_skill_examples(
        provider, skill_slug="my-skill", filenames=["basic.md", "advanced.md"], agent=_agent_ref(),
    )
    assert "Basic example" in result
    assert "Advanced example" in result
    assert "x = 1" in result
    assert "x = 2" in result


async def test_load_skill_examples_dedupe_and_missing(provider):
    agent = _agent_ref("session-C")
    await SkillIntegrationProvider.load_skill_examples(
        provider, skill_slug="my-skill", filenames=["basic.md"], agent=agent,
    )
    result = await SkillIntegrationProvider.load_skill_examples(
        provider, skill_slug="my-skill", filenames=["basic.md", "missing.md"], agent=agent,
    )
    assert "Already loaded" in result
    assert "Not found" in result
    assert "Available examples" in result


async def test_load_skill_examples_unknown_only(provider):
    result = await SkillIntegrationProvider.load_skill_examples(
        provider, skill_slug="my-skill", filenames=["nope.md"], agent=_agent_ref(),
    )
    assert "Not found" in result
