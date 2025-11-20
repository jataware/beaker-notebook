import contextvars
import inspect
import os
import hashlib
import logging
from dataclasses import dataclass, field
from functools import lru_cache, update_wrapper, wraps
from traitlets import Unicode, Bool
from typing import Optional

from jupyter_server.auth.authorizer import Authorizer
from jupyter_server.auth.identity import IdentityProvider, User
from tornado import web

from jupyter_server.services.config.manager import ConfigManager

current_user = contextvars.ContextVar("current_user", default=None)
current_request = contextvars.ContextVar("current_request", default=None)


class BeakerIdentityProvider(IdentityProvider):

    beaker_kernel_header = Unicode(
        "X-AUTH-BEAKER",
        help="Header name for Beaker kernel authentication",
        config=True
    )

    async def _is_authorized_beaker_kernel(self, handler: web.RequestHandler):
        """Validate Beaker kernel authentication token.

        Checks for a valid Beaker kernel authentication token in the request
        headers and validates it against the kernel's session key using MD5 hash.

        Parameters
        ----------
        handler : web.RequestHandler
            The Tornado request handler containing the authentication headers

        Returns
        -------
        bool
            True if the token is valid, False otherwise
        """
        auth_token = handler.request.headers.get(self.beaker_kernel_header, None)
        if not auth_token:
            return False

        try:
            preamble, kernel_id, nonce, hash_value = auth_token.split(':')
            if preamble != "beaker-kernel" or not kernel_id or not hash_value:
                return False
            kernel = handler.kernel_manager.get_kernel(kernel_id)
            key = kernel.session.key.decode()

            payload = f"{kernel_id}{nonce}{key}".encode()
            reconstructed_hash_value = hashlib.md5(payload).hexdigest()
            valid = reconstructed_hash_value == hash_value
            return valid

        except Exception as err:
            logging.error(err)
            return False


    @classmethod
    def beaker_kernel_auth_wrapper(cls, fn):
        """Decorator for Beaker kernel authentication wrapper.

        Wraps the get_user method to check for Beaker kernel authentication
        before falling back to the original authentication method.

        Parameters
        ----------
        fn : callable
            The original get_user method to wrap

        Returns
        -------
        callable
            Wrapped get_user method with Beaker kernel auth
        """
        @wraps(fn)
        async def get_user(self: BeakerIdentityProvider, handler: web.RequestHandler):
            is_beaker = await self._is_authorized_beaker_kernel(handler)
            if is_beaker:
                handler._token_authenticated = True
                return RoleBasedUser(
                    username="beaker_kernel_",
                    name="Beaker Kernel",
                    roles=["admin"],
                )
            else:
                result = fn(self, handler)
                if inspect.isawaitable(result):
                    result = await result
                return result
        return get_user

    def __init_subclass__(cls, **kwargs):
        """Setup authentication wrapper for subclasses.

        Automatically applies the Beaker kernel authentication wrapper
        to the get_user method of subclasses.

        Parameters
        ----------
        **kwargs
            Additional keyword arguments for subclass initialization
        """
        super().__init_subclass__(**kwargs)
        get_user = cls.beaker_kernel_auth_wrapper(cls.get_user)
        update_wrapper(get_user, cls.get_user)
        cls.get_user = get_user


class BeakerAuthorizer(Authorizer):
    pass


@dataclass
class BeakerUser(User):
    home_dir: Optional[str] = field(default=None)
    config: Optional[dict] = field(default=None)

    def __post_init__(self):
        """Initialize home directory if not provided.

        Automatically generates a sanitized home directory path
        based on the username if not explicitly set.
        """
        if self.home_dir is None:
            self.home_dir = self._sanitize_homedir(self.username)
        if self.config is None:
            # TODO: Fetch config from somewhere
            self.config = {}
        return super().__post_init__()

    @staticmethod
    def _sanitize_homedir(path_string: str):
        """Sanitize username for use as directory path.

        Removes invalid characters and creates a unique directory name
        by combining sanitized username with SHA1 hash.

        Parameters
        ----------
        path_string : str
            Original username string

        Returns
        -------
        str
            Sanitized directory path
        """
        # Characters invalid for a path
        invalid_chars = r'<>:"/\|?*@\'' + os.sep
        # Remove any whitespace or invalid characters from the start or end of path.
        stripped_path_string = path_string.strip().strip(invalid_chars)
        # Replace invalid characters with '_'
        sanitized_path = "".join(char if char not in invalid_chars else '_' for char in stripped_path_string)
        full_path = '_'.join((sanitized_path, hashlib.sha1(path_string.encode()).hexdigest()))
        return full_path


@dataclass
class BeakerPermission:
    name: str
    description: str = ""

@dataclass
class BeakerRole:
    name: str
    config: dict = field(default_factory=lambda: {})
    permissions: list[str] = field(default_factory=lambda: [])


@dataclass
class RoleBasedUser(BeakerUser):
    roles: list[str] = field(default_factory=lambda: [])
