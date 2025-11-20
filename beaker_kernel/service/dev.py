import inspect
import importlib
import logging
import os
import os.path
import subprocess
import sys

from watchdog.observers import Observer
from watchdog import events as watchdog_events

import beaker_kernel
from beaker_kernel.service.notebook import BeakerNotebookApp
from beaker_kernel.lib.autodiscovery import autodiscover
from beaker_kernel.lib.config import config


# Global notebook storage for notebook that lives for lifetime of service
notebook_content = None
logger = logging.getLogger(__file__)

app_subprocess = None


def _jupyter_server_extension_points():
    return [{"module": "beaker_kernel.service.dev", "app": DevBeakerJupyterApp}]


class DevBeakerJupyterApp(BeakerNotebookApp):
    def initialize_settings(self):
        # Override to allow cross domain websockets
        self.settings["allow_origin"] = "*"
        self.settings["disable_check_xsrf"] = True


class BeakerWatchDog(watchdog_events.FileSystemEventHandler):
    def __init__(self, observer, modules, callback=None) -> None:
        super().__init__()
        self.observer = observer
        self.modules = modules
        self.callback = callback

    def on_any_event(self, event):
        # Only restart based on specific message types below
        if not isinstance(
            event,
            (
                watchdog_events.FileModifiedEvent,
                watchdog_events.FileMovedEvent,
                watchdog_events.FileDeletedEvent,
                watchdog_events.FileCreatedEvent
            )
        ) or event.src_path == __file__:
            return super().on_any_event(event)

        # Only restart for changes to python files or procedure files
        if event.src_path.endswith(".py") or "procedures" in event.src_path:
            print(f"\n *** Detected a change in file {event.src_path} *** ")

            # Drain the queue, as we are restarting regardless of other changes:
            while not self.observer.event_queue.empty():
                self.observer.event_queue.get_nowait()

            # Try to reimport all the modules as a way to check if we will crash if we restart.
            try:
                for mod in self.modules:
                    importlib.reload(mod)
            except ImportError:
                logger.error("Error reloading")

            if self.callback:
                self.callback()


def create_observer(extra_dirs=None, callback=None):
    contexts = autodiscover("contexts")
    subkernels = autodiscover("subkernels")
    modules = set([inspect.getmodule(beaker_kernel)])
    modules.update([inspect.getmodule(cls) for _, cls in contexts.items()])
    modules.update([inspect.getmodule(cls) for _, cls in subkernels.items()])
    mod_paths = [os.path.dirname(inspect.getabsfile(mod)) for mod in modules]
    all_paths: list[str] = mod_paths[:]
    if extra_dirs:
        all_paths.extend([
            extra_dir for extra_dir in extra_dirs
            if os.path.exists(extra_dir)
        ])
    # Sort by length so we add more general paths before more specific/subpaths
    sorted_paths = sorted(all_paths, key=lambda f: len(f))
    paths = set()
    for path in sorted_paths:
        is_subpath = False
        for saved_path in paths:
            if path.startswith(saved_path):
                is_subpath = True
                break
        if not is_subpath:
            paths.add(path)

    print("Watching the following paths for modifications:")
    print("\n".join(f"  {path}" for path in paths))
    observer = Observer()
    handler = BeakerWatchDog(observer, modules, callback=callback)

    for path in paths:
        observer.schedule(event_handler=handler, path=path, recursive=True)
    observer.start()
    return observer

def main():
    # Fix up arguments
    args = sys.argv[:]
    debug = os.environ.get("DEBUG", False)
    if "--ip" not in args:
        args.extend(["--ip", "0.0.0.0"])
    if debug and debug.lower() not in ("0", "false", "f", "off") and "--debug" not in args:
        args.append("--debug")
    serverapp = DevBeakerJupyterApp.initialize_server(argv=args)
    serverapp.start()


if __name__ == "__main__":
    if "watch" in sys.argv:
        args = sys.argv[:]
        args.remove("watch")
        extra_dirs = []
        while "--extra_watch_dir" in args:
            idx = args.index("--extra_watch_dir")
            args.pop(idx)  # Pop the flag
            extra_dir = args.pop(idx)  # Value is now in the index where the flag was
            logger.warn(f"Adding extra watch dir {extra_dir}")
            extra_dirs.append(extra_dir)

        observer = create_observer(extra_dirs)
        try:
            while True:
                app_subprocess = subprocess.Popen([
                        sys.executable,
                        *args,
                    ],
                    env=os.environ
                )
                app_subprocess.wait()
        finally:
            if app_subprocess:
                logger.error("Shutting down subprocess...")
                app_subprocess.kill()
    else:
        main()
