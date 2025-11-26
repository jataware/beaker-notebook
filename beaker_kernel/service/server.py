from beaker_kernel.service.base import BaseBeakerApp


class BeakerServerApp(BaseBeakerApp):
    defaults = {
        "log_requests": True,
        "ip": "0.0.0.0",
        "allow_root": True,
        "MultiKernelManager": {
            "cull_idle_timeout": 3600,
        }
    }


if __name__ == "__main__":
    BeakerServerApp.launch_instance()
