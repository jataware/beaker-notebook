# Application interface layer

def __getattr__(name):
    if name == "BaseBeakerApp":
        from .base import BaseBeakerApp
        return BaseBeakerApp
    elif name == "BeakerServerApp":
        from .server_app import BeakerServerApp
        return BeakerServerApp
    elif name == "BeakerNotebookApp":
        from .notebook_app import BeakerNotebookApp
        return BeakerNotebookApp
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")