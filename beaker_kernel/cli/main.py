import click
import importlib

from beaker_kernel.lib.autodiscovery import find_mappings, autodiscover


class BeakerCli(click.Group):
    subcommands: dict[str, click.Command | click.Group]
    apps: dict[str, str]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.subcommands = {}
        self.apps = {}

        # Register commands from extensions
        for group_name, entry in autodiscover("commands").items():
            group = entry.as_group()
            self.subcommands[group_name] = group

        # Register Beaker app commands
        for app_name, entry in autodiscover("apps").items():
            if entry is None:
                continue
            self.apps[app_name] = f"{entry.__module__}.{entry.__name__}"

    def list_commands(self, ctx):
        commands = super().list_commands(ctx)
        commands.extend(self.subcommands.keys())
        commands.extend(self.apps.keys())
        return commands

    def get_command(self, ctx, cmd_name):
        if cmd_name in self.subcommands:
            return self.subcommands[cmd_name]
        elif cmd_name in self.apps:
            from .app import build_app_command
            import_str = self.apps[cmd_name]
            return build_app_command(cmd_name, import_str)
        else:
            return super().get_command(ctx, cmd_name)

@click.group(cls=BeakerCli)
def cli():
    """
    CLI Tooling to work with and in Beaker
    """
    pass


from .project import project
from .config import config_group
from .running import dev, notebook
from .server import server
from .context import context
from .subkernel import subkernel
from .app import app

cli.add_command(project)
cli.add_command(config_group)
cli.add_command(context)
cli.add_command(dev)
cli.add_command(server)
cli.add_command(notebook)
cli.add_command(subkernel)
cli.add_command(app)
