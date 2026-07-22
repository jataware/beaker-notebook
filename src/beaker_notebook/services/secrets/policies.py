import asyncio
import copy
from dataclasses import dataclass, field, is_dataclass, asdict
from typing import TYPE_CHECKING, Any, Awaitable, Callable, ClassVar, Collection, Literal, TypeAlias

from beaker_notebook.services.secrets.validations import Validation, not_in

if TYPE_CHECKING:
    from .types import BaseSecret

PolicyTypes: TypeAlias = Literal["redact", "remove", "last4", "allow"]

@dataclass
class BasePolicy:
    type: PolicyTypes
    validations: Collection[Validation] = field(default_factory=lambda: [not_in,])

    async def replacement(self, secret_str: str):
        raise NotImplementedError(f"Policy '{BasePolicy}' does not define a sanitize function")


    async def _sanitize_str(self, secret: "BaseSecret", content: str) -> str:
        secret_str = secret.get_value()
        replacement = await self.replacement(secret_str)
        sanitized = content.replace(secret_str, replacement)

        await asyncio.gather(*[
            validation_func(secret_str, sanitized) for validation_func in self.validations
        ])

        return sanitized

    async def _sanitize_list(self, secret: "BaseSecret", content: list) -> list:
        # Walk a list, sanitizing each item
        for idx, value in enumerate(content):
            match value:
                case str():
                    content[idx] = await self._sanitize_str(secret, value)
                case dict():
                    content[idx] = await self._sanitize_dict(secret, value)
                case list():
                    content[idx] = await self._sanitize_list(secret, value)
                case bytes():
                    content[idx] = (await self._sanitize_str(secret, value.decode())).encode()
                case _:
                    pass
        return content

    async def _sanitize_dict(self, secret: "BaseSecret", content: dict) -> dict:
        # Walk dict, looking for strings and do a sanitization on each string
        for key, value in content.items():
            match value:
                case str():
                    content[key] = await self._sanitize_str(secret, value)
                case dict():
                    content[key] = await self._sanitize_dict(secret, value)
                case list():
                    content[key] = await self._sanitize_list(secret, value)
                case bytes():
                    content[key] = (await self._sanitize_str(secret, value.decode())).encode()
                case _:
                    pass

    async def sanitize(self, secret: "BaseSecret", content: str|dict):
        target = copy.deepcopy(content)
        match target:
            case str() | bytes():
                return await self._sanitize_str(secret, target)
            case dict():
                return await self._sanitize_dict(secret, target)
            case list():
                return await self._sanitize_list(secret, target)
            case _:
                return content

@dataclass
class Allow(BasePolicy):
    """
    This policy does not modify the content in any way.
    Only for use in high-trust situations or debugging
    """

    type: PolicyTypes = "allow"

    # TODO: Add warning on initialization about this being insecure?

    async def sanitize(self, secret, content):
        return content


@dataclass
class Redact(BasePolicy):
    type: PolicyTypes = "redact"

    async def replacement(self, secret_str):
        return "#" * len(secret_str)


@dataclass
class Remove(BasePolicy):
    type: PolicyTypes = "remove"

    async def _sanitize_list(self, secret, content):
        secret_value = secret.get_value()
        while secret_value in content:
            content.remove(secret_value)
        return content

    async def _sanitize_dict(self, secret, content):
        name = getattr(secret, name, None)
        if name and name in content:
            content.pop(name)
        return content

    async def replacement(self, secret_str):
        return ""


@dataclass
class Last4(BasePolicy):
    type: PolicyTypes = "last4"

    async def replacement(self, secret_str):
        if len(secret_str) < 6:
            # Returning last four chars could is too much information for such a short secret.
            return "####"
        return f"###{secret_str[:-4]}"


