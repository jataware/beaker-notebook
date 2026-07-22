import contextvars
import hashlib
import hmac
import inspect
import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache, update_wrapper, wraps
from typing import Optional, TYPE_CHECKING

from jupyter_server.auth.authorizer import Authorizer
from jupyter_server.auth.identity import IdentityProvider, User
from traitlets import Bool, Unicode
from tornado import web

from jupyter_server.services.config.manager import ConfigManager

if TYPE_CHECKING:
    from beaker_notebook.services.secrets.types import BaseSecret

current_user = contextvars.ContextVar("current_user", default=None)
current_request = contextvars.ContextVar("current_request", default=None)


class BeakerIdentityProvider(IdentityProvider):

    beaker_kernel_header = Unicode(
        "X-AUTH-BEAKER",
        help="Header name for Beaker kernel authentication",
        config=True
    )

    def authenticated_beaker_kernel_id(self, handler: web.RequestHandler) -> Optional[str]:
        """Return the kernel ID from a valid Beaker kernel authentication token.

        Checks for a valid Beaker kernel authentication token in the request
        headers and validates it against the kernel's session key using SHA256 hash.

        Parameters
        ----------
        handler : web.RequestHandler
            The Tornado request handler containing the authentication headers

        Returns
        -------
        Optional[str]
            The authenticated kernel ID, or ``None`` when the token is absent
            or invalid.
        """
        auth_token = handler.request.headers.get(self.beaker_kernel_header, None)
        if not auth_token:
            return None

        try:
            preamble, kernel_id, nonce, hash_value = auth_token.split(':')
            if preamble != "beaker-kernel" or not kernel_id or not hash_value:
                return None
            kernel = handler.kernel_manager.get_kernel(kernel_id)
            key = kernel.session.key.decode()

            payload = f"{kernel_id}{nonce}{key}".encode()
            reconstructed_hash_value = hashlib.sha256(payload).hexdigest()
            if not hmac.compare_digest(reconstructed_hash_value, hash_value):
                return None
            return kernel_id

        except Exception as err:
            logging.error(err)
            return None

    def _is_authorized_beaker_kernel(self, handler: web.RequestHandler):
        """Validate a Beaker kernel authentication token."""
        return self.authenticated_beaker_kernel_id(handler) is not None


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
            is_beaker = self._is_authorized_beaker_kernel(handler)
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

                current_user.set(result)
                return result
        return get_user

    def is_token_authenticated(self, handler: web.RequestHandler) -> bool:
        return self._is_authorized_beaker_kernel(handler) or super().is_token_authenticated(handler)

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
    secrets: "list[BaseSecret]" = field(default_factory=list)

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
        # TODO: Populate user secrets
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
