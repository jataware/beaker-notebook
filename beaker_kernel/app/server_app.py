from beaker_kernel.app.base import BaseBeakerApp


class BeakerServerApp(BaseBeakerApp):
    defaults = {
        "log_requests": True,
        "ip": "0.0.0.0",
        "allow_root": True,
        "kernel_manager_class": "beaker_kernel.services.kernel.mappingmanager.BeakerDistributedKernelMappingManager",
        "datastore_class": "beaker_kernel.services.datastore.sqlite.Sqlite3Datastore",
        "MultiKernelManager": {
            "cull_idle_timeout": 3600,
        }
    }


if __name__ == "__main__":
    BeakerServerApp.launch_instance()
