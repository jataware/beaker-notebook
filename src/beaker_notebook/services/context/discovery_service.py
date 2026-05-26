import inspect
import traceback
from typing import ClassVar

import traitlets
from traitlets.config import SingletonConfigurable

from beaker_notebook.lib.context import BeakerContext, autodiscover_contexts


class ContextDiscoveryService(SingletonConfigurable):
    known_services: "ClassVar[dict[type[ContextDiscoveryService], ContextDiscoveryService|None]]" = {}
    registered_services: "ClassVar[list[ContextDiscoveryService]]" = []

    auto_register: bool = traitlets.Bool(default_value=False, config=True)

    def __init_subclass__(cls):
        super().__init_subclass__()
        # Replace defined "discover" classes as _discover
        if discover_func := getattr(cls, "discover", None):
            if inspect.ismethod(discover_func) and discover_func is not ContextDiscoveryService.discover:
                setattr(cls, "_discover", discover_func)
                delattr(cls, "discover")
        # Register  subclass as a known service
        ContextDiscoveryService.known_services[cls] = None
        return cls

    def setup_instance(self, *args, **kwargs):
        super().setup_instance(*args, **kwargs)
        # Only execute once on this superclass
        # TODO: Determine if we are confident that services will be registered by the time this is called.
        if self.__class__ is ContextDiscoveryService:
            kwargs["parent"] = self
            for cls, value in self.known_services.items():
                if value != None:
                    continue
                service: ContextDiscoveryService = cls.instance(**kwargs)
                if service.auto_register:
                    ContextDiscoveryService.known_services[cls] = service
                    ContextDiscoveryService.registered_services.append(service)

    def _discover(self, **kwargs) -> dict[str, BeakerContext]:
        raise NotImplementedError()

    def discover(self, **kwargs) -> dict[str, BeakerContext]:
        results = {}
        for service in self.registered_services:
            if isinstance(service, ContextDiscoveryService):
                try:
                    contexts: dict[str, BeakerContext] = service._discover(**kwargs)
                except Exception as err:
                    self.log.warning(
                        f"Error discovering contexts from service '{service}'({service.__class__.__module__}.{service.__class__.__name__}): {err}"
                    )
                    self.log.debug(traceback.format_exception(err))
                    continue
                for context_slug, context in contexts.items():
                    if context_slug in results:
                        prev_context = results[context_slug]
                        self.log.warning(
                            f"Duplicate context slug '{context_slug}' detected. Replacing "
                            f"{prev_context.__class__.__module__}.{prev_context.__class__.__name__} with "
                            f"{context.__class__.__module__}.{context.__class__.__name__}."
                        )
                    results[context_slug] = context
        return results


class LocalContextDiscoveryService(ContextDiscoveryService):
    """
    Context Discovery Service that returns locally installed contexts.
    """
    @traitlets.default("auto_register")
    def _default_auto_register(self):
        return True

    def _discover(self, **kwargs):
        return autodiscover_contexts()
