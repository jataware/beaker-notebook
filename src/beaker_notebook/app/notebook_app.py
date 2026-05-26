from beaker_kernel.app.base import BaseBeakerApp
from beaker_kernel.services.auth.notebook import NotebookAuthorizer, NotebookIdentityProvider


class BeakerNotebookApp(BaseBeakerApp):

    defaults = {
        "authorizer_class": NotebookAuthorizer,
        "identity_provider_class": NotebookIdentityProvider,
    }

if __name__ == "__main__":
    BeakerNotebookApp.launch_instance()
