"""Tests for the mutable SkillIntegrationProvider: creating, editing, removing,
and previewing skills, resource CRUD, on-disk discovery, and path validation.
"""
import json
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from beaker_notebook.lib.integrations.skill import (
    SkillIntegrationProvider,
    SKILL_RESOURCE_DIRS,
)
from beaker_notebook.lib.integrations.types import (
    SkillIntegration,
    SkillFileResource,
    SkillExampleResource,
    SkillMetadataResource,
    SkillInstructionsResource,
)

# Route regex for a resource id path segment (app/api/integrations.py). Resource
# ids must remain matchable here, i.e. contain no ':', '.', or '/'.
RESOURCE_ID_RE = re.compile(r"[\w\d-]+")


@pytest.fixture
def provider(tmp_path: Path, monkeypatch) -> SkillIntegrationProvider:
    """A provider whose search + writable roots are isolated to tmp_path and
    that starts with an empty catalog (no skills discovered)."""
    write_root = tmp_path / "writable"
    monkeypatch.setattr(
        SkillIntegrationProvider, "_candidate_write_roots",
        classmethod(lambda cls: [write_root]),
    )
    monkeypatch.setattr(
        "beaker_notebook.lib.integrations.skill.find_resource_dirs",
        lambda *a, **k: [],
    )
    monkeypatch.setattr(
        SkillIntegrationProvider, "_get_skill_search_roots",
        classmethod(lambda cls: []),
    )
    p = SkillIntegrationProvider(id="test-provider", skill_paths=[])
    p._test_write_root = write_root  # type: ignore[attr-defined]
    return p


def _mock_remote(text: str):
    response = MagicMock()
    response.text = text
    response.raise_for_status = MagicMock()
    return patch(
        "beaker_notebook.lib.integrations.skill.requests.get",
        return_value=response,
    )


REMOTE_MD = "---\nname: Remote Skill\ndescription: remote desc\nlicense: Apache-2.0\n---\n# Remote\n\nBody."


# ---------------------------------------------------------------------------
# add_integration (local)
# ---------------------------------------------------------------------------

class TestAddLocalSkill:
    def test_creates_skill_md_and_registers(self, provider):
        skill = provider.add_integration(
            name="My Skill",
            description="A test skill.",
            source_type="local",
            instructions="# My Skill\n\nDo the thing.",
        )
        assert isinstance(skill, SkillIntegration)
        assert skill.source_type == "local"
        assert skill in provider.list_integrations()
        skill_md = Path(skill.base_path) / "SKILL.md"
        assert skill_md.is_file()
        text = skill_md.read_text()
        assert "name: My Skill" in text
        assert "Do the thing." in text

    def test_deterministic_uuid(self, provider):
        skill = provider.add_integration(name="My Skill", description="d", source_type="local")
        assert skill.uuid == f"agent-skill:test-provider:{skill.slug}"

    def test_writes_frontmatter_fields(self, provider):
        skill = provider.add_integration(
            name="Meta Skill",
            description="d",
            source_type="local",
            license="MIT",
            compatibility="python>=3.11",
            allowed_tools="Bash, Read",
            skill_metadata={"author": "matt"},
        )
        text = (Path(skill.base_path) / "SKILL.md").read_text()
        assert "license: MIT" in text
        assert "compatibility: python>=3.11" in text
        assert "allowed-tools: Bash, Read" in text
        assert "author: matt" in text

    def test_lands_under_writable_root(self, provider):
        skill = provider.add_integration(name="Where", description="d", source_type="local")
        expected = provider._test_write_root / "skills" / skill.slug
        assert Path(skill.base_path).resolve() == expected.resolve()

    def test_duplicate_slug_raises(self, provider):
        provider.add_integration(name="Dup", description="d", source_type="local")
        with pytest.raises(ValueError):
            provider.add_integration(name="Dup", description="d2", source_type="local")

    def test_missing_name_raises(self, provider):
        with pytest.raises(ValueError):
            provider.add_integration(description="d", source_type="local")


# ---------------------------------------------------------------------------
# update_integration (local)
# ---------------------------------------------------------------------------

class TestUpdateLocalSkill:
    def test_rewrites_body_and_description(self, provider):
        skill = provider.add_integration(
            name="Edit Me", description="old", source_type="local",
            instructions="old body",
        )
        updated = provider.update_integration(
            skill.uuid, name="Edit Me", description="new", instructions="new body",
        )
        assert updated.uuid == skill.uuid  # identity stable
        assert updated.description == "new"
        text = (Path(updated.base_path) / "SKILL.md").read_text()
        assert "description: new" in text
        assert "new body" in text

    def test_preserves_metadata_when_omitted(self, provider):
        skill = provider.add_integration(
            name="Keep Meta", description="d", source_type="local",
            license="MIT", skill_metadata={"author": "matt"},
        )
        # Update only the description; license/metadata must survive.
        updated = provider.update_integration(skill.uuid, description="changed")
        meta = next(r for r in updated.resources.values() if isinstance(r, SkillMetadataResource))
        assert meta.license == "MIT"
        assert meta.skill_metadata == {"author": "matt"}


# ---------------------------------------------------------------------------
# remove_integration
# ---------------------------------------------------------------------------

class TestRemoveSkill:
    def test_local_deletes_dir_and_unregisters(self, provider):
        skill = provider.add_integration(name="Doomed", description="d", source_type="local")
        base = Path(skill.base_path)
        assert base.is_dir()
        provider.remove_integration(skill.uuid)
        assert not base.exists()
        assert all(s.uuid != skill.uuid for s in provider.list_integrations())


# ---------------------------------------------------------------------------
# Remote skills
# ---------------------------------------------------------------------------

class TestRemoteSkill:
    def test_add_writes_manifest_and_sets_url(self, provider):
        with _mock_remote(REMOTE_MD):
            skill = provider.add_integration(source_type="remote", url="https://ex.com/skill/")
        assert skill.source_type == "remote"
        assert skill.url == "https://ex.com/skill/"
        manifest = provider._test_write_root / "skills.json"
        assert "https://ex.com/skill/" in json.loads(manifest.read_text())

    def test_update_rewrites_manifest_url(self, provider):
        with _mock_remote(REMOTE_MD):
            skill = provider.add_integration(source_type="remote", url="https://ex.com/a/")
        with _mock_remote(REMOTE_MD):
            provider.update_integration(skill.uuid, url="https://ex.com/b/")
        manifest = provider._test_write_root / "skills.json"
        entries = json.loads(manifest.read_text())
        assert "https://ex.com/b/" in entries
        assert "https://ex.com/a/" not in entries

    def test_remove_removes_manifest_entry(self, provider):
        with _mock_remote(REMOTE_MD):
            skill = provider.add_integration(source_type="remote", url="https://ex.com/skill/")
        provider.remove_integration(skill.uuid)
        manifest = provider._test_write_root / "skills.json"
        assert "https://ex.com/skill/" not in json.loads(manifest.read_text())

    def test_resource_add_rejected_for_remote(self, provider):
        with _mock_remote(REMOTE_MD):
            skill = provider.add_integration(source_type="remote", url="https://ex.com/skill/")
        with pytest.raises(ValueError):
            provider.add_resource(
                skill.uuid, resource_type="skill_file",
                relative_path="references/x.md", content="x",
            )


# ---------------------------------------------------------------------------
# Preview (unsaved)
# ---------------------------------------------------------------------------

class TestPreview:
    def test_content_preview_not_persisted(self, provider):
        before = len(provider.list_integrations())
        skill = provider.add_integration(
            preview=True, source_type="local",
            content="---\nname: Preview\ndescription: d\nlicense: MIT\n---\n# body",
        )
        assert len(provider.list_integrations()) == before  # not added
        assert skill.name == "Preview"

    def test_content_preview_has_no_file_resources(self, provider):
        # A body that references files must NOT yield phantom skill_file resources
        # in a preview (base_path-less); the client enumerates the real files.
        skill = provider.add_integration(
            preview=True, source_type="local",
            content="---\nname: P\ndescription: d\n---\n# body\n\nSee [x](./reference/x.md).",
        )
        kinds = {r.resource_type for r in skill.resources.values()}
        assert kinds == {"skill_metadata", "skill_instructions"}

    def test_remote_preview_fetches_not_persisted(self, provider):
        before = len(provider.list_integrations())
        with _mock_remote(REMOTE_MD):
            skill = provider.add_integration(preview=True, source_type="remote", url="https://ex.com/s/")
        assert len(provider.list_integrations()) == before
        assert skill.name == "Remote Skill"

    def test_content_preview_requires_content(self, provider):
        with pytest.raises(ValueError):
            provider.add_integration(preview=True, source_type="local")


# ---------------------------------------------------------------------------
# Resource CRUD (local)
# ---------------------------------------------------------------------------

class TestResourceCRUD:
    def _skill(self, provider):
        return provider.add_integration(name="Res Skill", description="d", source_type="local")

    def test_add_skill_file_writes_and_registers(self, provider):
        skill = self._skill(provider)
        resource = provider.add_resource(
            skill.uuid, resource_type="skill_file",
            relative_path="references/guide.md", content="guide text",
        )
        assert isinstance(resource, SkillFileResource)
        assert (Path(skill.base_path) / "references/guide.md").read_text() == "guide text"
        assert resource.resource_id in skill.resources

    def test_add_skill_example_writes(self, provider):
        skill = self._skill(provider)
        resource = provider.add_resource(
            skill.uuid, resource_type="skill_example",
            filename="ex1.md", content="# Example One\n\ndesc",
        )
        assert isinstance(resource, SkillExampleResource)
        assert (Path(skill.base_path) / "examples/ex1.md").is_file()

    def test_resource_id_is_url_safe(self, provider):
        skill = self._skill(provider)
        resource = provider.add_resource(
            skill.uuid, resource_type="skill_file",
            relative_path="scripts/run.py", content="print(1)",
        )
        assert RESOURCE_ID_RE.fullmatch(resource.resource_id), resource.resource_id

    def test_update_resource_rewrites_content(self, provider):
        skill = self._skill(provider)
        resource = provider.add_resource(
            skill.uuid, resource_type="skill_file",
            relative_path="references/g.md", content="v1",
        )
        provider.update_resource(skill.uuid, resource.resource_id, content="v2")
        assert (Path(skill.base_path) / "references/g.md").read_text() == "v2"

    def test_remove_resource_deletes_file(self, provider):
        skill = self._skill(provider)
        resource = provider.add_resource(
            skill.uuid, resource_type="skill_file",
            relative_path="assets/a.txt", content="a",
        )
        provider.remove_resource(skill.uuid, resource.resource_id)
        assert not (Path(skill.base_path) / "assets/a.txt").exists()
        assert resource.resource_id not in skill.resources

    def test_singular_reference_dir_accepted(self, provider):
        skill = self._skill(provider)
        provider.add_resource(
            skill.uuid, resource_type="skill_file",
            relative_path="reference/node.md", content="node",
        )
        assert (Path(skill.base_path) / "reference/node.md").read_text() == "node"

    @pytest.mark.parametrize("bad_path", [
        "../escape.md",
        "/abs/path.md",
        "references/../../escape.md",
        "notadir/x.md",
    ])
    def test_invalid_relative_path_rejected(self, provider, bad_path):
        skill = self._skill(provider)
        with pytest.raises(ValueError):
            provider.add_resource(
                skill.uuid, resource_type="skill_file",
                relative_path=bad_path, content="x",
            )


# ---------------------------------------------------------------------------
# On-disk discovery / scan behavior
# ---------------------------------------------------------------------------

class TestDiscoveryScan:
    def _write_skill(self, root: Path, name: str, body: str, files: dict[str, str]) -> Path:
        d = root / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: d\n---\n{body}")
        for rel, content in files.items():
            fp = d / rel
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(content)
        return d

    def test_local_files_from_disk_scan(self, tmp_path, monkeypatch):
        skill_dir = self._write_skill(
            tmp_path, "scan-skill", "# body (no file references)",
            {"references/a.md": "a", "scripts/b.py": "b", "reference/c.md": "c"},
        )
        monkeypatch.setattr(
            "beaker_notebook.lib.integrations.skill.find_resource_dirs", lambda *a, **k: [])
        skill = SkillIntegrationProvider._load_local_skill(str(skill_dir))
        paths = {r.relative_path for r in skill.resources.values() if isinstance(r, SkillFileResource)}
        # All on-disk files enumerated even though the body references none.
        assert paths == {"references/a.md", "scripts/b.py", "reference/c.md"}

    def test_local_ignores_body_only_references(self, tmp_path, monkeypatch):
        # SKILL.md references a file that is NOT on disk -> must not appear.
        skill_dir = self._write_skill(
            tmp_path, "phantom-skill", "See [x](references/missing.md).", {},
        )
        monkeypatch.setattr(
            "beaker_notebook.lib.integrations.skill.find_resource_dirs", lambda *a, **k: [])
        skill = SkillIntegrationProvider._load_local_skill(str(skill_dir))
        file_resources = [r for r in skill.resources.values() if isinstance(r, SkillFileResource)]
        assert file_resources == []

    def test_remote_uses_body_references(self, provider):
        body_md = "---\nname: R\ndescription: d\n---\n# body\n\nUse `references/guide.md`."
        with _mock_remote(body_md):
            skill = provider._load_remote_skill("https://ex.com/s/")
        paths = {r.relative_path for r in skill.resources.values() if isinstance(r, SkillFileResource)}
        assert "references/guide.md" in paths


# ---------------------------------------------------------------------------
# Context corpus namespacing (drives the read-only gate on the frontend)
# ---------------------------------------------------------------------------

class TestContextCorpus:
    def test_context_provider_namespaces_corpus(self, tmp_path, monkeypatch):
        d = tmp_path / "skills" / "ctx-skill"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text("---\nname: ctx-skill\ndescription: d\n---\n# body")
        monkeypatch.setattr(
            "beaker_notebook.lib.integrations.skill.find_resource_dirs", lambda *a, **k: [])
        monkeypatch.setattr(
            SkillIntegrationProvider, "_get_skill_search_roots",
            classmethod(lambda cls: [tmp_path]))
        provider = SkillIntegrationProvider(id="context-weather")
        skill = provider.list_integrations()[0]
        assert skill.corpus == "context-weather"
        assert skill.uuid.startswith("agent-skill:context-weather:")
