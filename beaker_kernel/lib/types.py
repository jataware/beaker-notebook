import inspect
import os
import typing
from beaker_kernel.lib.utils import slugify, to_import_string
from collections import deque
from dataclasses import dataclass, field, is_dataclass, Field
from datetime import date, datetime
from itertools import islice
from typing import get_origin, get_args, Mapping, Collection
from uuid import uuid4

from beaker_kernel.lib.utils import import_dotted_class
from beaker_kernel.lib.workflow import Workflow

if typing.TYPE_CHECKING:
    from beaker_kernel.lib.context import BeakerContext
    from beaker_kernel.lib.agent import BeakerAgent
    from beaker_kernel.lib.subkernel import BeakerSubkernel
    # from beaker_kernel.lib.integrations.base import Integration


def is_action(target: typing.Any) -> bool:
    """Utility to determine if an object is an action method/function"""
    return callable(target) and hasattr(target, "_action")

def is_tool(target: typing.Any) -> bool:
    """Utility to determine if an object is an tool method/function"""
    return callable(target) and hasattr(target, "_is_tool")


IntegrationTypes: typing.TypeAlias = typing.Literal["api", "database", "dataset", "skill"]


@dataclass(kw_only=True)
class Resource:
    resource_type: typing.ClassVar[str]
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
    slug: typing.Optional[str] = field(default=None)
    datatype: IntegrationTypes = field(default="api")
    url: typing.Optional[str] = field(default=None)
    img_url: typing.Optional[str] = field(default=None)
    source: typing.Optional[str] = field(default=None, metadata={"terse-action": ("truncate", 30)})
    last_updated: typing.Optional[datetime|date] = field(default=None)

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


@dataclass
class ProcedureInfo:
    slug: str
    name: str
    languages: list[str]
    description: typing.Optional[str] = field(default=None)


@dataclass
class ToolInfo:
    name: str
    description: str
    doc_string: str
    is_autosummarized: bool
    arguments: list[tuple]
    return_info: tuple

    @classmethod
    def from_func(cls, func):
        return cls(
            name=func._name,
            description=func._desc[0],
            doc_string=func.__doc__.strip(),
            is_autosummarized=func.autosummarize,
            arguments=[(arg_name, str(arg_type), arg_desc, other) for arg_name, arg_type, arg_desc, other in func._args_list],
            return_info=(func._ret[0], str(func._ret[1]), func._ret[2]),
        )


@dataclass
class ActionInfo:
    name: str           # fn._action
    documentation: str  # fn._docs
    scope: str          # fn._scope

    @classmethod
    def from_func(cls, func):
        return cls(
            name=func._action,
            documentation=func._docs,
            scope=func._scope,
        )


@dataclass
class SubkernelInfo:
    cls: str
    slug: str
    display_name: str
    description: str
    kernel_name: str
    language: str
    tools: dict[str, ToolInfo]
    weight: int

    @classmethod
    def from_class(cls, subkernel_cls: "type[BeakerSubkernel]", metadata=None):
        if metadata is None:
            metadata = {}
        return cls(
            cls=to_import_string(subkernel_cls),
            slug=subkernel_cls.SLUG,
            display_name=subkernel_cls.DISPLAY_NAME,
            description=getattr(subkernel_cls, "DESCRIPTION", subkernel_cls.__doc__),
            kernel_name=subkernel_cls.KERNEL_NAME,
            language=subkernel_cls.JUPYTER_LANGUAGE,
            tools={
                tool._name: ToolInfo.from_func(tool)
                for _, tool in inspect.getmembers(subkernel_cls, is_tool)
            },
            weight=subkernel_cls.WEIGHT,
        )


@dataclass
class LanguageInfo:
    slug: str
    display_name: str


@dataclass
class LLMInfo:
    model_provider: str
    model_name: str


@dataclass
class AgentInfo:
    cls: str
    description: str
    tools: dict[str, ToolInfo]
    agent_prompt: str
    version: typing.Optional[str] = field(default=None)

    @classmethod
    def from_class(cls, agent_cls: "type[BeakerAgent]", metadata=None):
        if metadata is None:
            metadata = {}
        tools = {
            tool._name: ToolInfo.from_func(tool)
            for _, tool in inspect.getmembers(agent_cls, is_tool)
        }
        result = cls(
            cls=to_import_string(agent_cls),
            description=agent_cls.__doc__,
            tools=tools,
            agent_prompt="PROMPT"
        )
        return result

def truncate(target, size=None):
    match target:
        case str():
            size = size or 50
            return target[:size] + "..."
        case list():
            size = size or 2
            return target[:size] + ["..."]
        case tuple():
            size = size or 2
            return target[:size] + ("...",)
        case dict():
            size = size or 0
            return {
                **{key: value for key, value in islice(target.items(), size)},
                "_truncated_rows": max((len(target) - size), 0)
            }
        case _:
            return "..."


def reify_dataclasses(target, typedef=None, verbose: bool = True):
    if typedef is None:
        typedef = type(target)

    if target is None:
        return target

    elif is_dataclass(typedef):
        values = {}

        # Replace generic type with specific subclass if defined in dict as subclass may have extra fields
        if isinstance(target, dict) and "_obj_cls" in target:
            typedef = import_dotted_class(target.get("_obj_cls"))

        for field_name, field_def in typedef.__dataclass_fields__.items():
            if isinstance(target, typedef):
                value = getattr(target, field_name)
            elif isinstance(target, dict):
                value = target.get(field_name)
            if not verbose and (terse_action := getattr(field_def, "metadata", {}).get("terse-action", None)):
                match terse_action:
                    case "exclude":
                        continue
                    case "set-null":
                        value = None
                        field_def = type(None)
                    case ("truncate", int(x)):
                        value = truncate(value, x)
                    case "truncate":
                        value = truncate(value)
                        field_def = type(value)
                    case _:
                        value = value
            values[field_name] = (field_def, value)

        if isinstance(target, typedef):
            for field_name, (field_type, field_value) in values.items():
                if isinstance(field_type, Field):
                    field_type = field_type.type
                setattr(target, field_name, reify_dataclasses(field_value, field_type, verbose=verbose))
        elif isinstance(target, dict):
            instance_cls = import_dotted_class(target.pop("_obj_cls")) if "_obj_cls" in target else typedef
            target = reify_dataclasses(
                instance_cls(**{name: value for name, (_, value) in values.items()}),
                instance_cls,
                verbose=verbose
            )
        elif target is None:
            return None
        else:
            raise ValueError(f"Unable to map {repr(target)} to type {typedef}")
        return target
    else:
        # All others, return the value so that that the dataclass attribute is replaced with the new value
        origin = get_origin(typedef) or (typedef if isinstance(typedef, type) else type(target))
        args = get_args(typedef) or [None, None]
        if not isinstance(origin, type):
            return target
        if issubclass(origin, Mapping):
            return {key: reify_dataclasses(value, args[1], verbose=verbose) for key, value in target.items()}
        elif issubclass(origin, (list, tuple, set)):
            return origin(reify_dataclasses(value, args[0], verbose=verbose) for value in target)
        else:
            return target

@dataclass
class ContextInfo:
    slug: str
    short_name: str
    full_name: str
    cls: str
    description: str
    weight: int

    agent: AgentInfo
    actions: dict[str, ActionInfo]
    tools: dict[str, ToolInfo]
    integrations: dict[str, dict[str, Integration]]
    workflows: dict[str, Workflow]
    subkernels: dict[str, SubkernelInfo]
    languages: dict[str, LanguageInfo]
    procedures: dict[str, ProcedureInfo]

    asset_dir: typing.Optional[os.PathLike|str|bytes]
    has_renderers: bool

    version: typing.Optional[str] = field(default=None)
    last_updated: datetime = field(default_factory=datetime.now)
    metadata: dict[str, typing.Any] = field(default_factory=lambda: {})

    @classmethod
    def from_class(cls, context_cls: "type[BeakerContext]", metadata=None, verbose=True):
        if metadata is None:
            metadata = {}

        # Fetch subkernels from class
        subkernels = {
            slug: SubkernelInfo.from_class(subkernel)
            for slug, subkernel in context_cls.available_subkernels().items()
        }
        agent = AgentInfo.from_class(context_cls.AGENT_CLS)

        # Build out full list of tools with increasing priority
        tools = {}
        for subkernel in subkernels.values():
            tools.update(subkernel.tools)
        tools.update(agent.tools)
        tools.update({
            tool._name: ToolInfo.from_func(tool)
            for _, tool in inspect.getmembers(context_cls, is_tool)
        })


        # Fetch workflow information from class
        procedures = {
            proc_slug: ProcedureInfo(
                slug=proc_slug,
                name=proc.get("name", proc_slug),
                languages=proc.get("languages", []),
                description=proc.get("description", None),
            ) for
            proc_slug, proc in context_cls.discover_procedures().items()
        }

        # Derive languages from subkernels
        languages = {
            subkernel.slug: LanguageInfo(slug=subkernel.slug, display_name=subkernel.slug.title())
            for subkernel in subkernels.values()
        }

        # Fetch workflow information from class
        integrations = {}
        for integration_provider in getattr(context_cls, "integration_providers", []):
            provider_integrations = {}
            for integration_key, integration in integration_provider.discover_integrations().items():
                integration.location = str(integration.location)
                provider_integrations[integration_key] = integration
            integrations[integration_provider.slug] = provider_integrations

        # Fetch workflow information from class
        workflows = context_cls.discover_workflows()

        asset_dir = context_cls.ASSET_DIR
        has_renderers = context_cls.RENDERERS is not None

        # Build output class
        result = cls(
            slug=context_cls.SLUG,
            short_name=context_cls.SHORT_NAME,
            full_name=context_cls.FULL_NAME,
            cls=to_import_string(context_cls),
            description=context_cls.__doc__,  # TODO: Improve this
            weight=getattr(context_cls, "WEIGHT", None),
            agent=agent,
            actions={
                action._action: ActionInfo.from_func(action)
                for _, action in inspect.getmembers(context_cls, is_action)
            },
            tools=tools,
            workflows=workflows,
            integrations=integrations,
            subkernels=subkernels,
            languages=languages,
            asset_dir=asset_dir,
            has_renderers=has_renderers,
            procedures=procedures,
            metadata=metadata,
        )
        return result
