import logging
from functools import lru_cache
from traitlets import Unicode, Bool

from jupyter_server.auth.identity import User

from . import BeakerAuthorizer, BeakerIdentityProvider, RoleBasedUser, current_request, current_user



class DummyIdentityProvider(BeakerIdentityProvider):

    async def get_user(self, handler) -> User|None:
        current_request.set(handler.request)
        user = RoleBasedUser(
            username="test@test-user.com",
            name="testuser",
            display_name="Test User",
            roles=["admin"],
        )
        logging.debug(f"User: {user}")
        current_user.set(user)
        return user



class DummyAuthorizer(BeakerAuthorizer):
    def is_authorized(self, handler, user, action, resource):
        return 'admin' in user.roles


authorizer = DummyAuthorizer
identity_provider = DummyIdentityProvider
