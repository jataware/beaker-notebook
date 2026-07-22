from typing import TYPE_CHECKING, Any, Awaitable, Callable, ClassVar, Collection, Literal, TypeAlias


Validation: TypeAlias = Callable[[str, str], Awaitable[None]]


class SecretValidationError(Exception):
    pass


async def not_in(secret_str: str, content: str) -> None:
    if secret_str in content:
        raise SecretValidationError()
