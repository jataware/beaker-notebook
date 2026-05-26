import typing

from beaker_notebook.services import ServiceApi, ServiceApiHandler, HTTPError

if typing.TYPE_CHECKING:
    from .manager import BeakerContextManager


class ContextApi(ServiceApi):
    prefix = r"contexts"

    class ContextInfo(ServiceApiHandler):
        pattern = r"(?P<context_slug>\w+)?"

        @property
        def context_manager(self) -> "BeakerContextManager":
            context_manager = getattr(self.serverapp, "context_manager", None)
            if context_manager is None:
                raise HTTPError(404, "Context manager not found")
            return context_manager

        async def get(self, context_slug=None):

            if self.request.arguments.get("update", False):
                self.log.info("Updating contexts per request")
                self.context_manager.update_contexts()

            if context_slug:
                verbose = self.request.arguments.get("verbose", True)
                result = self.context_manager.get_context(context_slug, verbose=verbose)
                if result is None:
                    raise HTTPError(404, f"Context with slug '{context_slug}' not found.")
            else:
                verbose = self.request.arguments.get("verbose", False)
                result = self.context_manager.list_contexts(verbose=verbose)
            self.write(result)
