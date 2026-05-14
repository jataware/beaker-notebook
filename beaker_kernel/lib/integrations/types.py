import typing
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Any, Literal, Optional, TypeAlias, Union
from uuid import uuid4

from beaker_kernel.lib.utils import slugify


IntegrationTypes: TypeAlias = Literal["api", "database", "dataset", "skill"]


@dataclass(kw_only=True)
class Resource:
    resource_type: str = "generic"
    integration: typing.Optional[str] = None
    # optional -- if not included on handwritten yaml, it will be generated
    resource_id: typing.Optional[str] = None
    def __post_init__(self):
        if self.resource_id is None:
            self.resource_id = str(uuid4())


@dataclass(kw_only=True)
class FileResource(Resource):
    resource_type: str = "file"
    # user facing name
    name: str
    # optional - None could be an unsaved new file held in memory but not on disk
    filepath: typing.Optional[str] = field(default=None)
    # TODO: encoding?
    content: typing.Optional[str] = field(default=None)


@dataclass(kw_only=True)
class ExampleResource(Resource):
    resource_type: str = "example"
    query: str
    code: str
    notes: typing.Optional[str] = field(default=None)


@dataclass
class IntegrationExample:
    query: str
    code: str
    notes: typing.Optional[str]

@dataclass(kw_only=True)
class SkillMetadataResource(Resource):
    """Parsed SKILL.md frontmatter fields."""
    resource_type: str = "skill_metadata"
    skill_name: str
    skill_slug: str
    description: str
    license: typing.Optional[str] = None
    compatibility: typing.Optional[str] = None
    allowed_tools: typing.Optional[str] = None
    skill_metadata: dict[str, str] = field(default_factory=dict)


@dataclass(kw_only=True)
class SkillInstructionsResource(Resource):
    """The markdown body of SKILL.md (everything after frontmatter)."""
    resource_type: str = "skill_instructions"
    content: str


@dataclass(kw_only=True)
class SkillFileResource(Resource):
    """A file from the skill's scripts/, references/, or assets/ directories."""
    resource_type: str = "skill_file"
    name: str
    relative_path: str
    content: typing.Optional[str] = field(default=None)


@dataclass(kw_only=True)
class SkillExampleResource(Resource):
    """A code example from the skill's examples/ directory."""
    resource_type: str = "skill_example"
    filename: str
    title: str
    description: str
    content: typing.Optional[str] = field(default=None)


@dataclass
class Integration:
    name: str
    description: str
    provider: str
    resources: dict[str, Resource] = field(default_factory=lambda: {}, metadata={"terse-action": "truncate"})
    uuid: str = field(default_factory=lambda: str(uuid4()))

    # created if not present -- UUID! but must be easily json serializable
    slug: str = field(default_factory=lambda: typing.cast(str, None))
    # slug: typing.Optional[str] = field(default=None)
    datatype: IntegrationTypes = field(default="api")
    url: typing.Optional[str] = field(default=None)
    img_url: typing.Optional[str] = field(default=None)
    source: typing.Optional[str] = field(default=None, metadata={"terse-action": ("truncate", 30)})
    last_updated: typing.Optional[datetime|date] = field(default=None)

    # --- Curation fields (used by the integration filter system) ---
    # Tags applied to this integration. Tags inherited from a parent corpus
    # (when applicable) are merged in at load time so callers can filter on
    # `tags` directly without traversing the corpus tree.
    tags: list[str] = field(default_factory=list)
    # Slug of the parent corpus, if this integration was declared inside one.
    # `None` for top-level entries. Surfaces in the UI tree and as a filter
    # matcher (`corpus:<slug>`).
    corpus: Optional[str] = field(default=None)
    # Optional natural-language guidance about when this integration is the
    # right choice. Surfaced to the agent in the foundational prompt alongside
    # `description`. Authored by the integration / skill author.
    selection_instructions: Optional[str] = field(default=None)
    # Free-form author metadata. Distinct from runtime fields above; available
    # as filter matchers (`metadata:<key>=<value>`).
    extra_metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def slugify(cls, name: str):
        return slugify(name)

    def __post_init__(self):
        if self.slug is None:
            self.slug = self.slugify(self.name)

    def add_resources(self, resource_list: list[Resource]):
        for resource in resource_list:
            if resource.resource_id:
                self.resources[resource.resource_id] = resource


@dataclass
class SkillIntegration(Integration):
    """An integration backed by an Agent Skill."""
    datatype: IntegrationTypes = "skill"
    source_type: str = "local"  # "local" or "remote"
    base_path: typing.Optional[str] = None
    base_url: typing.Optional[str] = None
    # Additional instructions appended to the skill's SKILL.md body when
    # `load_skill_instructions` is invoked. Authored at the skills.json layer
    # (see `SkillEntryConfig.extra_instructions`) and resolved to a string at
    # load time regardless of whether the source was inline text or a path.
    extra_instructions: typing.Optional[str] = None


# ---------------------------------------------------------------------------
# skills.json configuration schema
#
# A skills.json file is a list of entries. Each entry is either:
#   - a bare string (legacy/simple form: a local path or http(s) URL to a
#     skill), or
#   - an object form (`SkillEntryConfig` or `CorpusEntryConfig`) that adds
#     curation fields (tags, corpus membership, disabled flag, etc.).
#
# These dataclasses describe the *config file* schema. Runtime objects
# (Integration, Corpus) are produced from them by the provider.
# ---------------------------------------------------------------------------


@dataclass(kw_only=True)
class SkillEntryConfig:
    """Object form of a skill entry in skills.json.

    The `source` field accepts the same values a bare-string entry accepts
    (relative path, absolute path, or http(s) URL); the form is autodetected.
    """
    kind: Literal["skill"] = "skill"
    source: str
    # Hard-disable. Skill is not loaded at all; it never becomes an
    # Integration and is never surfaced in prompts or the UI.
    disabled: bool = False
    # Natural-language guidance for the agent about when to pick this skill.
    # Merged into the foundational prompt next to the skill's own description.
    selection_instructions: Optional[str] = None
    # Tags applied to this skill. Merged with any tags inherited from a
    # parent corpus at load time.
    tags: list[str] = field(default_factory=list)
    # Free-form author metadata; available as filter matchers.
    metadata: dict[str, Any] = field(default_factory=dict)
    # Additional instructions appended to the loaded SKILL.md body. May be
    # an inline string or a path to a file containing the text. Resolved at
    # load time. Appended after the SKILL.md body and before the examples
    # listing.
    extra_instructions: Optional[str] = None


@dataclass(kw_only=True)
class CorpusEntryConfig:
    """A named grouping of skills (and/or nested corpora) in skills.json.

    Corpora exist for organization and selection: they appear as collapsible
    groups in the UI, are filterable via the `corpus:<slug>` matcher, and
    propagate their `tags` to descendants at load time.
    """
    kind: Literal["corpus"] = "corpus"
    # Stable identifier surfaced in the UI and in filter matchers. Required.
    slug: str
    # Human-readable name (defaults to a title-cased `slug`).
    name: Optional[str] = None
    # Surfaced in the foundational prompt so the agent can decide whether to
    # activate this corpus.
    description: str
    # Either an inline list of entries, or a path (string) to a nested
    # skills.json file with the same top-level schema. The path form lets a
    # corpus be a thin pointer to a curated bundle published elsewhere.
    entries: "Union[list[SkillsConfigEntry], str]"
    # Hard-disable the entire corpus and all descendants. Nothing inside
    # becomes an Integration.
    disabled: bool = False
    # Hard-disable specific descendant entries by their slug / name. Useful
    # when consuming an upstream corpus you don't control and you want to
    # exclude a small number of entries without forking the bundle.
    disabled_children: list[str] = field(default_factory=list)
    # Natural-language guidance for when to activate this corpus.
    selection_instructions: Optional[str] = None
    # Tags applied to every descendant of this corpus at load time.
    tags: list[str] = field(default_factory=list)
    # Free-form author metadata; available as filter matchers.
    metadata: dict[str, Any] = field(default_factory=dict)


# An entry in skills.json. The bare-string form remains supported for
# backwards compatibility and quick declarations; object forms unlock the
# curation fields above.
SkillsConfigEntry: TypeAlias = Union[str, SkillEntryConfig, CorpusEntryConfig]

# The root of a skills.json document.
SkillsConfigFile: TypeAlias = list[SkillsConfigEntry]


@dataclass
class Corpus:
    """Runtime representation of a corpus.

    Produced from `CorpusEntryConfig` (or synthesized for the implicit
    "User Skills" / "Context Skills" groupings the UI uses to attribute
    sources). Corpora are surfaced in the foundational prompt, can be
    targeted by filter rules, and form the tree the UI renders.
    """
    slug: str
    name: str
    description: str
    parent: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    selection_instructions: Optional[str] = None
    extra_metadata: dict[str, Any] = field(default_factory=dict)
    # Slugs of integrations and child corpora that belong to this corpus.
    # Membership is derived at load time from the config tree.
    integration_slugs: list[str] = field(default_factory=list)
    child_corpus_slugs: list[str] = field(default_factory=list)
