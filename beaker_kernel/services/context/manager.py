import inspect
import sys
from dataclasses import is_dataclass, asdict
from typing import TYPE_CHECKING, TypeAlias

import traitlets
from traitlets import Instance, Type, default
from traitlets.config.configurable import LoggingConfigurable
from traitlets.utils.importstring import import_item

from beaker_kernel.lib.context import BeakerContext
from beaker_kernel.lib.types import ContextInfo
from beaker_kernel.lib.utils import to_import_string
from beaker_kernel.services import ServiceApi
from beaker_kernel.services.context.handlers import ContextApi
from beaker_kernel.services.context.util import find_differences
from beaker_kernel.services.datastore import Column, ColumnType, DatastoreTable, Now, TableRecord
from beaker_kernel.services.datastore.records import TableDict

if TYPE_CHECKING:
    from beaker_kernel.app.base import BaseBeakerApp
    from beaker_kernel.services.context.discovery_service import ContextDiscoveryService


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
        Column(name="weight", column_type=ColumnType.INTEGER),
        Column(name="version", column_type=ColumnType.TEXT, allow_null=True),

        # Info
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
        def dict_factory(*args, **kwargs):
            try:
                # Fetch raw object that is being turned into a dict so we can keep track of its type
                frame = inspect.currentframe()
                if frame:
                    parent_frame = frame.f_back
                    obj_cls = parent_frame.f_locals.get("obj", None)
                    if obj_cls:
                        kwargs.setdefault("_obj_cls", to_import_string(obj_cls))
            except Exception as err:
                pass
            obj = dict(*args, **kwargs)
            return obj

        if is_dataclass(resource):
            record = asdict(resource, dict_factory=dict_factory)
        else:
            return resource
        return record

    def deserialize(self, record: "ContextRecord", parent: "BeakerContextManager", verbose: bool = True) -> ContextInfo:
        cls: type = import_item(record["cls"])
        from beaker_kernel.lib.types import reify_dataclasses
        return reify_dataclasses(
            ContextInfo(
                slug=record["slug"],
                short_name=record["short_name"],
                full_name=record["full_name"],
                cls=cls,
                description=record["description"],
                weight=record.get("weight", None),
                version=record.get("version", None),
                actions=record["actions"],
                tools=record["tools"],
                agent=record["agent"],
                integrations=record["integrations"],
                workflows=record["workflows"],
                subkernels=record["subkernels"],
                languages=record["languages"],
                procedures=record["procedures"],
                metadata=record["metadata"],
            ),
            verbose=verbose,
        )


ContextRecord: TypeAlias = TableRecord[ContextTable]


class BeakerContextManager(LoggingConfigurable):
    parent: "BaseBeakerApp"

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
    api_cls = Type(
        default_value=ContextApi,
        klass=ServiceApi,
        config=True
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.update_contexts()
        self.parent.handlers.extend(self.api_cls.handlers)

    def update_contexts(self):
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
        if isinstance(context, BeakerContext):
            # record: ContextRecord = self.context_table.serialize(ContextInfo.from_instance(context))
            context = context.__class__
        if isinstance(context, type) and issubclass(context, BeakerContext):
            record = self.context_table.serialize(ContextInfo.from_class(context, verbose=True))
        else:
            record = self.context_table.serialize(context)
        existing_record = self.context_table.get(slug=record["slug"])
        if existing_record:
            differences = find_differences(existing_record, record)
            if {key for key in differences if key != "last_updated"}:
                self.log.debug(f"Updating context {record['slug']} with differences: {differences}")
                return self.context_table.update(conditions={"slug": record["slug"]}, record=record)
            else:
                self.log.debug(f"Context {record['slug']} already registered with the same data, skipping update.")
                return existing_record
        else:
            return self.context_table.add(record)

    def list_contexts(self, verbose: bool = False) -> list[ContextInfo]:
        return [self.context_table.deserialize(record, self, verbose=verbose) for record in self.context_table.all()] or []

    def get_context(self, slug: str, verbose: bool = True) -> ContextInfo|None:
        record = self.context_table.get(slug=slug)
        return self.context_table.deserialize(record, self, verbose=verbose) or None
