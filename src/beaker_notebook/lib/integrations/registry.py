from collections.abc import Iterable, Iterator

from beaker_notebook.lib.integrations.base import BaseIntegrationProvider
from beaker_notebook.lib.utils import ensure_async


class IntegrationProviderRegistry:
    """Iterable container of integration providers, folded to one instance per class.

    Every consumer treats a provider *class* as a single logical provider, so
    the registry keeps exactly one instance per class and folds any extras into
    it via ``cls.merge``.

    The binding reason for that invariant is tool registration: the agent adds
    each provider instance as a tool container (see ``BeakerAgent.__init__``),
    and a provider's ``@tool`` methods are named by class/method. Two live
    instances of the same class would therefore expose duplicate,
    identically-named tools bound to *different* catalogs, leaving the agent no
    way to know which to call. Folding collapses them into one instance whose
    tools span the merged catalog. (Slug uniqueness, which ``list_providers``
    and ``call_in_context`` rely on, falls out of the same invariant but is not
    the driver.) This is why several config sources of the same kind — e.g. the
    default skills plus a context's own skills — are constructed as separate
    instances yet surface as one provider.

    Iteration order reflects insertion order; the first-added instance of a
    class is the merge winner (its ``id`` and other non-mergeable state survive)
    and later same-class instances are absorbed into it. ``display_name`` is
    class-level, so the resulting label does not depend on which instance wins.
    """

    def __init__(self, providers: Iterable[BaseIntegrationProvider] = ()):
        self._by_class: dict[type, BaseIntegrationProvider] = {}
        for provider in providers:
            self.add(provider)

    def add(self, provider: BaseIntegrationProvider) -> None:
        cls = type(provider)
        existing = self._by_class.get(cls)
        if existing is None:
            self._by_class[cls] = provider
        else:
            self._by_class[cls] = cls.merge(existing, provider)

    def __iter__(self) -> Iterator[BaseIntegrationProvider]:
        return iter(self._by_class.values())

    def __len__(self) -> int:
        return len(self._by_class)

    def __bool__(self) -> bool:
        return bool(self._by_class)

    def __contains__(self, provider: object) -> bool:
        if not isinstance(provider, BaseIntegrationProvider):
            return False
        return self._by_class.get(type(provider)) is provider

    async def system_preamble(self) -> str | None:
        if not self._by_class:
            return None
        integrations_by_provider: list[tuple[str, str]] = []
        for cls, provider in self._by_class.items():
            result = await ensure_async(provider.system_preamble())
            if result:
                integrations_by_provider.append((cls.display_name or provider.slug, result))
        if not integrations_by_provider:
            return None
        return "## Integrations\n\n" + "\n\n".join(f"### {provider_name}\n\n{content}" for provider_name, content in integrations_by_provider)
