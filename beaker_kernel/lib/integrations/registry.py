from collections.abc import Iterable, Iterator

from beaker_kernel.lib.integrations.base import BaseIntegrationProvider


class IntegrationProviderRegistry:
    """Iterable container of providers that folds same-class providers via cls.merge.

    Iteration order reflects insertion order; the first-added instance of a class
    is the merge winner (its id, display_name, and other non-mergeable state
    survive), and subsequent instances of the same class are absorbed into it.
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
