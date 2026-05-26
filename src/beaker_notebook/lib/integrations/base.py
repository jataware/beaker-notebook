import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable, ClassVar, Optional, Generator, Mapping
from typing_extensions import Self
from uuid import uuid4

from beaker_kernel.lib.integrations.types import Integration, Resource
from beaker_kernel.lib.autodiscovery import find_resource_dirs

class BaseIntegrationProvider(ABC):

    provider_type: ClassVar[str]
    mutable: ClassVar[bool] = False
    display_name: ClassVar[str]
    slug: ClassVar[str]

    id: str

    prompt_instructions: Optional[str]

    def __init__(self, display_name: Optional[str] = None, id: Optional[str] = None):
        if display_name is not None:
            self.__class__.display_name = display_name
        self.id = id if id is not None else str(uuid4())
        self.prompt_instructions = None

    @classmethod
    def get_cls_data(cls) -> dict[str, os.PathLike]:
        return {}

    async def system_preamble(self) -> Optional[str]:
        """Contribution to the cacheable system_preamble layer.

        Default delegates to the deprecated ``prompt`` property so existing
        providers keep working unchanged. New providers should override this
        method directly.
        """
        return self.prompt

    @property
    def prompt(self):
        integration_doc = self.__doc__ or ""
        parts = [
            f"Integration Name: {self.display_name}",
            "Integration description:",
            f"\t{integration_doc}",
        ]
        if self.prompt_instructions:
            parts.append(self.prompt_instructions)
        tools = self.tools
        if tools:
            parts.append("Provided tools:")
            for tool in tools:
                parts.append(f"\t{tool.name}")
        integrations = self.list_integrations()
        for integration in integrations:
            parts.append(str(integration))
        return "\n".join(parts)

    @classmethod
    def _merge(cls, a: Self, b: Self) -> Self:
        raise NotImplementedError(
            f"{cls.__name__} does not support merging; registering two "
            f"instances in the same context is ambiguous."
        )

    @classmethod
    def merge(cls, a: Self, b: Self) -> Self:
        """Combine two providers of this class into one. Default refuses; override to opt in."""
        if type(a) is not cls or type(b) is not cls:
            raise TypeError(
                f"{cls.__name__}.merge requires both arguments to be {cls.__name__} "
                f"instances (got {type(a).__name__}, {type(b).__name__})"
            )
        if a is b:
            # It's the same object, so just return either of them
            return a
        return cls._merge(a, b)

    @classmethod
    @abstractmethod
    def discover_integrations(cls, **kwargs) -> Mapping[str, Integration]:
        ...

    @classmethod
    def iter_data(cls, data_types: Optional[list[str] | str]=None) -> Generator[Path, None, None]:
        seen: set[tuple[str, str]] = set()
        if data_types is None:
            data_types = cls.get_cls_data().keys()
        elif isinstance(data_types, str):
            data_types = [data_types]
        for data_path_base in cls.get_data_basedirs():
            for data_type in data_types:
                type_path = Path(data_path_base) / data_type
                # Skip if generated path is not a directory
                if not type_path.is_dir():
                    continue
                for data_result in type_path.iterdir():
                    # Skip if seen a file of type and name already
                    key = (data_type, data_result.name)
                    if key in seen:
                        continue
                    seen.add(key)
                    yield data_result

    def get_file(self, data_type: str, name: os.PathLike) -> Optional[Path]:
        if os.path.isabs(name):
            raise IOError("Files retrieved by get_file cannot be absolute.")
        for data_dir in self.iter_data([data_type]):
            name_path = Path(name)
            # First check if file exists in path
            file_path = data_dir / name_path
            if file_path.exists():
                return file_path
            # If not, trim overlap of paths between the two paths.
            for i in range(len(data_dir.parts)):
                suffix = data_dir.parts[i:]  # possible overlap
                if name_path.parts[:len(suffix)] == suffix:
                    name_path = Path(*name_path.parts[len(suffix):])
                    break
            # Check if joined version with removed overlap exists.
            file_path = data_dir / name_path
            if file_path.exists():
                return file_path
        return None

    @classmethod
    def get_data_basedirs(cls, slug: Optional[str] = None) -> list[os.PathLike]:
        data_dirs = []
        if slug is None:
            slug = cls.slug
        for data_dir in find_resource_dirs("data"):
            base_dir = os.path.join(data_dir, slug)
            if os.path.isdir(base_dir):
                data_dirs.append(base_dir)
        alt_integration_dir = os.environ.get("INTEGRATION_PATH", "./integrations")
        if os.path.isdir(alt_integration_dir):
            data_dirs.append(alt_integration_dir)
        # Reverse dirs so we go from most specific to user to most general (global installs, etc)
        # This allows user to overwrite defaults
        data_dirs.reverse()
        return data_dirs

    @property
    def data_basedirs(self):
        return self.get_data_basedirs(self.slug)

    @abstractmethod
    def list_integrations(self) -> list[Integration]:
        ...

    @abstractmethod
    def get_integration(self, integration_id: str) -> Integration:
        ...

    @abstractmethod
    def list_resources(self, integration_id: str, resource_type: Optional[str] = None) -> list[Resource]:
        ...

    @abstractmethod
    def get_resource(self, integration_id: str, resource_id: str) -> Resource:
        ...

    @property
    def tools(self) -> list[Callable]:
        tools = []
        for member_name in dir(self):
            # dir evaluates prompt due to @property
            if member_name == "tools" or member_name == "prompt":
                continue
            member = getattr(self, member_name)
            if callable(member) and getattr(member, '_is_tool', False):
                tools.append(member)
        return tools


class MutableBaseIntegrationProvider(BaseIntegrationProvider):
    mutable = True

    @abstractmethod
    def add_integration(self, **payload) -> Integration:
        ...

    @abstractmethod
    def update_integration(self, integration_id: str, **payload) -> Integration:
        ...

    @abstractmethod
    def remove_integration(self, integration_id: str, **payload) -> None:
        ...

    @abstractmethod
    def add_resource(self, integration_id: str, **payload) -> Resource:
        ...

    @abstractmethod
    def update_resource(self, integration_id: str, resource_id: str, **payload) -> Resource:
        ...

    @abstractmethod
    def remove_resource(self, integration_id: str, resource_id: str, **payload) -> None:
        ...
