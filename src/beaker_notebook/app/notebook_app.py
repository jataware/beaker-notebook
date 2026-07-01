from pathlib import Path

from beaker_notebook.app.base import BaseBeakerApp
from beaker_notebook.services.auth.notebook import NotebookAuthorizer, NotebookIdentityProvider
from beaker_notebook.services.storage import BEAKER_LOCAL_DATA_PATH


SNAPSHOT_PATH = Path(BEAKER_LOCAL_DATA_PATH / "notebooks").resolve()


class BeakerNotebookApp(BaseBeakerApp):

    defaults = {
        "authorizer_class": NotebookAuthorizer,
        "identity_provider_class": NotebookIdentityProvider,
        "FileNotebookManager": {
            "snapshot_path": str(SNAPSHOT_PATH)
        }
    }

if __name__ == "__main__":
    BeakerNotebookApp.launch_instance()
