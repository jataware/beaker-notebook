import copy
import inspect
import os
from dataclasses import dataclass, is_dataclass, asdict
from typing import TYPE_CHECKING, Any, Collection, Literal, TypeAlias

import traitlets
from traitlets import Type, default
from traitlets.config.configurable import LoggingConfigurable
from traitlets.utils.importstring import import_item

from beaker_notebook.services.secrets.policies import PolicyTypes, BasePolicy, Allow, Redact, Remove
from beaker_notebook.services.secrets.types import BaseSecret, EnvironmentSecret, UserEnvironmentSecret, SystemEnvironmentSecret, is_env_secret, is_system_env_secret, is_user_env_secret


if TYPE_CHECKING:
    from beaker_notebook.app.base import BaseBeakerApp
    from beaker_notebook.lib.context import BeakerContext
    from beaker_notebook.services.auth import BeakerUser


class BeakerSecretsManager(LoggingConfigurable):
    parent: "BaseBeakerApp"

    _secrets: list[BaseSecret]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._secrets = []

    def add_secret(self, secret: BaseSecret):
        if secret in self._secrets:
            return
        self._secrets.append(secret)

    def add_secrets(self, secrets: Collection[BaseSecret]):
        for secret in secrets:
            self.add_secret(secret)

    async def sanitize_kernel_environment_vars(self, env: dict) -> dict[str, str]:
        result = copy.copy(env)
        for secret in self._secrets:
            policy = secret.subkernel_environment_policy
            if is_env_secret(secret) and secret.name in result:
                if isinstance(policy, Allow):
                    continue
                elif isinstance(policy, Remove):
                    result.pop(secret.name)
                else:
                    result[secret.name] = await policy.sanitize(secret, result[secret.name])
        return result

    async def sanitize_subkernel_envionment_vars(self, user: "BeakerUser", env: dict) -> dict[str, str]:
        result = copy.copy(env)
        if user and user.secrets:
            self.add_secrets(user.secrets)
        for secret in self._secrets:
            policy = secret.subkernel_environment_policy
            if is_env_secret(secret) and secret.name in result:
                if isinstance(policy, Allow):
                    continue
                elif isinstance(policy, Remove):
                    result.pop(secret.name)
                else:
                    result[secret.name] = await policy.sanitize(secret, result[secret.name])
            if is_user_env_secret(secret) and secret.name not in result:
                # Add the user secret to the environment if it doesn't exist TODO: Determine if this is the right thing
                result[secret.name] = secret.get_value()
        return result


    def _secret_env_vars(self) -> list[str]:
        sensitive_env_keys = set()
        anywhere = (
            "secret",
            "private",
            "password",
            "passwd",
            "creds",
            "credentials",
            "token",
            "auth",
            "passphrase",
        )
        suffix = (
            "_key",
            "_key_id",
        )
        for key in os.environ.keys():
            lkey = key.lower()
            if any((
                any(substr in lkey for substr in anywhere),
                lkey.endswith(suffix),
            )):
                sensitive_env_keys.add(key)
        return sorted(sensitive_env_keys)

    async def collect_system_secrets(self, app: "BaseBeakerApp") -> list[BaseSecret]:
        system_secrets = []
        system_secrets.extend(
            SystemEnvironmentSecret(name=env_name) for env_name in self._secret_env_vars()
        )
        # TODO: Extract secrets from app config
        # TODO: Extract secrets from beaker config
        return system_secrets


