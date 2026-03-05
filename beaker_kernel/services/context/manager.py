import inspect
from dataclasses import is_dataclass, asdict
from typing import TYPE_CHECKING

import traitlets
from traitlets import Type, default
from traitlets.config.configurable import LoggingConfigurable
from traitlets.utils.importstring import import_item

from beaker_kernel.lib.context import BeakerContext
from beaker_kernel.lib.types import ContextInfo
from beaker_kernel.lib.utils import to_import_string
from beaker_kernel.services import ServiceApi
from beaker_kernel.services.context.handlers import ContextApi
from beaker_kernel.services.context.util import find_differences

if TYPE_CHECKING:
    from beaker_kernel.app.base import BaseBeakerApp
    from beaker_kernel.services.context.discovery_service import ContextDiscoveryService


class BeakerContextManager(LoggingConfigurable):
    parent: "BaseBeakerApp"

    context_discovery_class = traitlets.DottedObjectName(
        "beaker_kernel.services.context.discovery_service.ContextDiscoveryService",
        config=True,
    )
    context_discovery_service: "ContextDiscoveryService" = traitlets.Instance(
        klass="beaker_kernel.services.context.discovery_service.ContextDiscoveryService",
    )
    api_cls = Type(
        default_value=ContextApi,
        klass=ServiceApi,
        config=True
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._contexts: dict[str, dict] = {}
        self.update_contexts()
        self.parent.handlers.extend(self.api_cls.handlers)

    def update_contexts(self):
        for context in self.context_discovery_service.discover().values():
            self.register_context(context)

    @default("context_discovery_service")
    def _default_context_discovery_service(self):
        from traitlets.config import SingletonConfigurable
        cls: SingletonConfigurable = traitlets.import_item(self.context_discovery_class)
        instance = cls.instance(parent=self)
        return instance

    def _serialize_context(self, context_info: ContextInfo) -> dict:
        """Convert a ContextInfo dataclass to a dict for storage."""
        def dict_factory(*args, **kwargs):
            try:
                frame = inspect.currentframe()
                if frame:
                    parent_frame = frame.f_back
                    obj_cls = parent_frame.f_locals.get("obj", None)
                    if obj_cls:
                        kwargs.setdefault("_obj_cls", to_import_string(obj_cls))
            except Exception:
                pass
            obj = dict(*args, **kwargs)
            return obj

        if is_dataclass(context_info):
            return asdict(context_info, dict_factory=dict_factory)
        return context_info

    def _deserialize_context(self, record: dict, verbose: bool = True) -> ContextInfo:
        """Convert a stored dict back to a ContextInfo."""
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

    def register_context(self, context: type[BeakerContext] | BeakerContext | ContextInfo) -> dict:
        if isinstance(context, BeakerContext):
            context = context.__class__
        if isinstance(context, type) and issubclass(context, BeakerContext):
            record = self._serialize_context(ContextInfo.from_class(context, verbose=True))
        else:
            record = self._serialize_context(context)
        slug = record["slug"]
        existing_record = self._contexts.get(slug)
        if existing_record:
            differences = find_differences(existing_record, record)
            if {key for key in differences if key != "last_updated"}:
                self.log.debug(f"Updating context {slug} with differences: {differences}")
                self._contexts[slug] = record
                return record
            else:
                self.log.debug(f"Context {slug} already registered with the same data, skipping update.")
                return existing_record
        else:
            self._contexts[slug] = record
            return record

    def list_contexts(self, verbose: bool = False) -> list[ContextInfo]:
        return [self._deserialize_context(record, verbose=verbose) for record in self._contexts.values()]

    def get_context(self, slug: str, verbose: bool = True) -> ContextInfo | None:
        record = self._contexts.get(slug)
        if record is None:
            return None
        return self._deserialize_context(record, verbose=verbose)
