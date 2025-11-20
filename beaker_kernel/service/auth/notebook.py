import logging
from functools import lru_cache
from traitlets import Unicode, Bool

from jupyter_server.auth.identity import User, IdentityProvider
from jupyter_server.auth.authorizer import Authorizer, AllowAllAuthorizer

from . import BeakerAuthorizer, BeakerIdentityProvider, RoleBasedUser, current_request, current_user



class NotebookIdentityProvider(BeakerIdentityProvider, IdentityProvider):
    def get_user(self, handler):
        return super().get_user(handler)


class NotebookAuthorizer(BeakerAuthorizer, AllowAllAuthorizer):
    pass


authorizer = NotebookAuthorizer
identity_provider = NotebookIdentityProvider
