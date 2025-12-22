import inspect
import itertools
import json
from collections import defaultdict
from dataclasses import dataclass, field, is_dataclass, asdict
from typing import TYPE_CHECKING, Any, TypeAlias

import traitlets
from traitlets import Instance, Type, default
from traitlets.config.configurable import LoggingConfigurable
from traitlets.utils.importstring import import_item

from beaker_kernel.app.base import BaseBeakerApp
from beaker_kernel.lib.context import BeakerContext
from beaker_kernel.services.datastore import Column, ColumnType, DatastoreTable, Now, TableRecord
from beaker_kernel.services.datastore.records import TableDict

if TYPE_CHECKING:
    from beaker_kernel.services.context.discovery_service import ContextDiscoveryService


# @dataclass
# class BeakerContextToolInfo:
#     name: str
#     description: str

# @dataclass
# class BeakerContextAgentInfo:
#     name: str
#     description: str

# @dataclass
# class BeakerContextIntegrationInfo:
#     name: str
#     description: str


# @dataclass
# class BeakerContextWorkflowInfo:
#     name: str
#     description: str


# @dataclass
# class BeakerContextSubkernelInfo:
#     name: str
#     description: str


# @dataclass
# class BeakerContextLanguageInfo:
#     name: str
#     description: str


# @dataclass
# class BeakerContextInfo:
#     slug: str
#     short_name: str
#     full_name: str
#     cls: type
#     description: str
#     version: str
#     agent: BeakerContextAgentInfo
#     actions: dict[str, BeakerContextToolInfo]
#     tools: dict[str, BeakerContextToolInfo]
#     integrations: dict[str, BeakerContextIntegrationInfo]
#     workflows: dict[str, BeakerContextWorkflowInfo]
#     subkernels: dict[str, BeakerContextSubkernelInfo]
#     languages: dict[str, BeakerContextLanguageInfo]
#     metadata: dict[str, Any] = field(default_factory=lambda: {})

from beaker_kernel.lib.types import (
    ActionInfo,
    AgentInfo,
    ContextInfo,
    Integration,
    LanguageInfo,
    LLMInfo,
    ProcedureInfo,
    SubkernelInfo,
    ToolInfo,
    Workflow,
    WorkflowStage,
    WorkflowStep,
)


class ContextTable(DatastoreTable):
    resource = ContextInfo
    name = "contexts"
    columns = [
        # Identity
        Column(name="slug", column_type=ColumnType.TEXT, allow_null=False),
        Column(name="short_name", column_type=ColumnType.TEXT, allow_null=False),
        Column(name="full_name", column_type=ColumnType.TEXT, allow_null=False),
        Column(name="cls", column_type=ColumnType.TEXT, allow_null=False),
        Column(name="description", column_type=ColumnType.TEXT),
        Column(name="version", column_type=ColumnType.TEXT, allow_null=True),

        Column(name="agent", column_type=ColumnType.JSON),
        Column(name="actions", column_type=ColumnType.JSON),
        Column(name="tools", column_type=ColumnType.JSON),
        Column(name="integrations", column_type=ColumnType.JSON),
        Column(name="workflows", column_type=ColumnType.JSON),
        Column(name="subkernels", column_type=ColumnType.JSON),
        Column(name="languages", column_type=ColumnType.JSON),
        Column(name="procedures", column_type=ColumnType.JSON),

        # Metadata
        Column(name="last_updated", column_type=ColumnType.DATETIME, default_value=Now()),
        Column(name="metadata", column_type=ColumnType.JSON, default_value="{}"),
    ]

    def serialize(self, resource: ContextInfo) -> "ContextRecord":
        if is_dataclass(resource):
            record = asdict(resource)
        return record

    def deserialize(self, record: "ContextRecord", parent: "BeakerContextManager") -> ContextInfo:
        cls: type = import_item(record["cls"])

        def objectify(value: Any):
            if isinstance(value, str):
                return json.loads(value)

        return ContextInfo(
            slug=record["slug"],
            short_name=record["short_name"],
            full_name=record["full_name"],
            cls=cls,
            description=record["description"],
            version=record.get("version", None),
            actions=objectify(record["actions"]),
            tools=objectify(record["tools"]),
            agent=objectify(record["agent"]),
            integrations=objectify(record["integrations"]),
            workflows=objectify(record["workflows"]),
            subkernels=objectify(record["subkernels"]),
            languages=objectify(record["languages"]),
            procedures=objectify(record["procedures"]),
            metadata=objectify(record["metadata"]),
        )


ContextRecord: TypeAlias = TableRecord[ContextTable]


class BeakerContextManager(LoggingConfigurable):
    parent: "BaseBeakerApp"
    # context_manager_class = traitlets.DottedObjectName(
    #     "beaker_context.services.context.manager.BeakerDistributedcontextManager",
    #     config=True,
    # )
    context_discovery_class = traitlets.DottedObjectName(
        "beaker_kernel.services.context.discovery_service.ContextDiscoveryService",
        config=True,
    )
    context_discovery_service: "ContextDiscoveryService" = traitlets.Instance(
        klass="beaker_kernel.services.context.discovery_service.ContextDiscoveryService",
    )
    context_table_class = Type(
        default_value=ContextTable,
        klass=DatastoreTable,
    )
    context_table = Instance(
        klass=DatastoreTable,
    )
    _contexts = Instance(
        klass=TableDict,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for context in self.context_discovery_service.discover().values():
            self.register_context(context)

    @default("_contexts")
    def _default_contexts(self):
        return TableDict(self.context_table, parent=self)

    @default("context_table")
    def _default_context_table(self):
        return self.context_table_class(datastore=self.parent.datastore)

    @default("context_discovery_service")
    def _default_context_discovery_service(self):
        from traitlets.config import SingletonConfigurable
        cls: SingletonConfigurable = traitlets.import_item(self.context_discovery_class)
        instance = cls.instance(parent=self)
        return instance

    def register_context(self, context: type[BeakerContext]|BeakerContext|ContextInfo) -> ContextRecord:

        def is_different(left, right) -> bool:
            if isinstance(left, dict) and isinstance(right, dict):
                left_keys = set(left.keys())
                right_keys = set(right.keys())
                left_keys.discard("last_updated")
                right_keys.discard("last_updated")

                if left_keys != right_keys:
                    return True

                for key in left_keys:
                    if is_different(left[key], right[key]):
                        return True
                # Same keys and values (ignoring last_updated), so they are not different
                return False
            elif isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
                if len(left) != len(right):
                    return True
                return any(is_different(left_item, right_item) for left_item, right_item in zip(left, right))
            else:
                return left != right

        def find_differences(prev: dict, new: dict) -> dict:
            result = {}
            for key in new.keys():
                if key == "last_updated":
                    continue
                if is_different(prev.get(key, None), new[key]):
                    result[key] = new[key]
            return result

        if isinstance(context, BeakerContext):
            # record: ContextRecord = self.context_table.serialize(ContextInfo.from_instance(context))
            context = context.__class__
        if isinstance(context, type) and issubclass(context, BeakerContext):
            record = self.context_table.serialize(ContextInfo.from_class(context))
        else:
            record = self.context_table.serialize(context)
        existing_record = self.context_table.get(slug=record["slug"])
        if existing_record:
            # differences = {k: v for k, v in record.items() if v != existing_record[k]}
            differences = find_differences(existing_record, record)
            if {key for key in differences if key != "last_updated"}:
                self.log.warning(f"Updating context {record['slug']} with differences: {differences}")
                return self.context_table.update(conditions={"slug": record["slug"]}, record=record)
            else:
                self.log.debug(f"Context {record['slug']} already registered with the same data, skipping update.")
                return existing_record
        else:
            return self.context_table.add(record)

    def list_contexts(self) -> list[ContextInfo]:
        return [self.context_table.deserialize(record, self) for record in self.context_table.all()]

    def get_context(self, slug: str) -> ContextInfo:
        record = self.context_table.get(slug)
        return self.context_table.deserialize(record, self)


def to_context_info(context_cls: type[BeakerContext]|BeakerContext) -> ContextInfo:
    """
    Context class (or instance) to context info object

    :param context: Description
    :type context: BeakerContext
    :return: Description
    :rtype: ContextInfo
    """
    if not isinstance(context_cls, type):
        context_cls = context_cls.__class__
    if not issubclass(context_cls, BeakerContext):
        raise ValueError(f"Context {context_cls} is not a subclass of BeakerContext")

    actions = {}
    tools = {}
    integrations = {}
    workflows = {}
    subkernels = context_cls.available_subkernels()
    language_map = defaultdict(list)
    for subkernel in subkernels.values():
        language_map[subkernel.JUPYTER_LANGUAGE] = subkernel

    agent_cls = getattr(context_cls, "AGENT_CLS", None)
    tool_classes = [context_cls]

    if agent_cls:
        tool_classes.append(agent_cls)

    for member_name, member in itertools.chain(inspect.getmembers(context_cls), inspect.getmembers(agent_cls)):
        if hasattr(member, "_action"):
            actions[member_name] = member
        elif getattr(member, "_is_tool", False):
            tools[member_name] = member

    context_info = ContextInfo(
        slug=context_cls.SLUG,
        short_name=context_cls.SHORT_NAME,
        full_name=context_cls.FULL_NAME,
        cls=context_cls.__class__,
        description=getattr(context_cls, "description", None),
        version=getattr(context_cls, "version", None),
        actions=actions or {},
        # actions=getattr(context_cls, "actions", {}),
        tools=tools or {},
        # tools=getattr(context_cls, "tools", {}),
        agent=getattr(context_cls, "agent", None),
        integrations=getattr(context_cls, "integrations", {}),
        workflows=getattr(context_cls, "workflows", {}),
        subkernels=subkernels or {},
        # subkernels=getattr(context_cls, "subkernels", {}),
        languages=getattr(context_cls, "languages", {}),
        # metadata=context.metadata,
    )
    return context_info
