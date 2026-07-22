import os

from dataclasses import dataclass, field, is_dataclass, asdict
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Optional, TypeAlias, Type, TypeIs

from beaker_notebook.services.auth import BeakerUser
from beaker_notebook.services.secrets.policies import BasePolicy, Allow, Redact, Remove

if TYPE_CHECKING:
    pass


PolicyRef: TypeAlias = BasePolicy | Type[BasePolicy]


@dataclass(kw_only=True)
class BaseSecret:
    type: ClassVar[str] = "base-secret"

    subkernel_message_policy: PolicyRef
    ui_message_policy: PolicyRef
    agent_message_policy: PolicyRef
    beaker_kernel_environment_policy: PolicyRef
    subkernel_environment_policy: PolicyRef

    def __post_init__(self, *args, **kwargs):
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if isinstance(value, type) and issubclass(value, BasePolicy):
                setattr(self, name, value())

    def get_value(self) -> Optional[str]:
        raise NotImplementedError()


@dataclass(kw_only=True)
class EnvironmentSecret(BaseSecret):
    type = "env-secret"
    agent_message_policy: PolicyRef = Redact
    subkernel_message_policy: PolicyRef = Redact
    ui_message_policy: PolicyRef = Redact

    name: str

    def get_value(self):
        return os.environ.get(self.name)


@dataclass(kw_only=True)
class SystemEnvironmentSecret(EnvironmentSecret):
    subkernel_message_policy: PolicyRef = Redact
    ui_message_policy: PolicyRef = Redact
    beaker_kernel_environment_policy: PolicyRef = Allow
    subkernel_environment_policy: PolicyRef = Remove

    def get_value(self):
        import os
        return os.environ.get(self.name)


@dataclass(kw_only=True)
class UserEnvironmentSecret(EnvironmentSecret):
    subkernel_message_policy: PolicyRef = Allow
    ui_message_policy: PolicyRef = Allow
    beaker_kernel_environment_policy: PolicyRef = Remove
    subkernel_environment_policy: PolicyRef = Allow

    user: Optional[BeakerUser] = None

    def get_value(self):
        return "USER ENV VALUE"


@dataclass(kw_only=True)
class SkillSecret(BaseSecret):
    type: str = "skill-secret"
    skill_name: str
    name: str
    default_value: Optional[str]

    def get_value(self):
        return os.environ.get(self.name)


def is_env_secret(secret: BaseSecret) -> TypeIs[EnvironmentSecret]:
    return isinstance(secret, EnvironmentSecret)

def is_system_env_secret(secret: BaseSecret) -> TypeIs[SystemEnvironmentSecret]:
    return isinstance(secret, SystemEnvironmentSecret)

def is_user_env_secret(secret: BaseSecret) -> TypeIs[UserEnvironmentSecret]:
    return isinstance(secret, UserEnvironmentSecret)

