from .server import BeakerServerApp

class BeakerMultiUserServerApp(BeakerServerApp):

    _default_app_traits = {
        "authorizer_class": "beaker_kernel.service.auth.dummy.DummyAuthorizer",
        "identity_provider_class": "beaker_kernel.service.auth.dummy.DummyIdentityProvider",
    }


if __name__ == "__main__":
    BeakerMultiUserServerApp.launch_instance()
