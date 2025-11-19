import os
import subprocess
import sys
from typing import TYPE_CHECKING

import click
import webbrowser

if TYPE_CHECKING:
    from beaker_kernel.service.notebook import BeakerNotebookApp


def set_config_from_app(app: "BeakerNotebookApp"):
    os.environ.setdefault("JUPYTER_SERVER", app.connection_url)
    os.environ.setdefault("JUPYTER_TOKEN", app.identity_provider.token)


@click.command(context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
@click.argument("extra_args", nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def notebook(ctx, extra_args, beakerapp_cls=None):
    """
    Start Beaker in local mode and opens a notebook.
    """
    from beaker_kernel.service.notebook import BeakerNotebookApp
    from beaker_kernel.lib.config import config
    from jupyter_core.utils import ensure_event_loop
    app = None
    loop = ensure_event_loop()
    try:
        app = BeakerNotebookApp.instance(**{"IdentityProvider.token": config.jupyter_token})
        app.initialize(argv=extra_args)
        config.jupyter_server = app.connection_url
        set_config_from_app(app)
        app.start()
    except (InterruptedError, KeyboardInterrupt, EOFError) as err:
        print(err)
    finally:
        if app:
            app.stop()
        loop.close()


@click.group(name="dev", invoke_without_command=True)
@click.option("--no-open-notebook", "-n", is_flag=True, default=False, type=bool, help="Prevent opening the notebook in a webbrowser.")
@click.pass_context
def dev(ctx: click.Context, no_open_notebook):
    """
    Start Beaker server in development mode. (Subcommands available)
    """
    # Don't run if we are running watch
    if ctx.invoked_subcommand is None:
        # Invert the default behavior around opening the notebook as `watch` has an opposite default.
        ctx.params["open_notebook"] = not ctx.params.pop("no_open_notebook")
        # Invoke watch as default action
        ctx.forward(watch)
        return


@dev.command(context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
@click.argument("extra_args", nargs=-1, type=click.UNPROCESSED)
@click.option("--open-notebook", "-n", is_flag=True, default=False, type=bool, help="Open a notebook in a webbrowser.")
def serve(open_notebook, extra_args):
    from jupyter_core.utils import ensure_event_loop
    from beaker_kernel.service.dev import BeakerNotebookApp

    loop = ensure_event_loop()
    try:
        app = BeakerNotebookApp.instance()
        set_config_from_app(app)
        app.initialize(argv=extra_args)
        if open_notebook:
            webbrowser.open(app.public_url)
        app.start()
    finally:
        app.stop()
        loop.close()


@dev.command(context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
@click.option("--extra_dir", multiple=True)
@click.option("--open-notebook", "-n", is_flag=True, default=False, type=bool, help="Open a notebook in a webbrowser.")
@click.argument("extra_args", nargs=-1, type=click.UNPROCESSED)
def watch(extra_dir=None, open_notebook=None, extra_args=None):
    from beaker_kernel.service.dev import create_observer
    app_subprocess = None
    extra_args = extra_args or []

    def restart():
        click.echo(" *** Restarting service *** \n")
        app_subprocess.terminate()

    observer = create_observer(extra_dir, restart)
    try:
        while True:
            try:
                args = [
                    sys.executable,
                    sys.argv[0], "dev", "serve", *extra_args
                ]
                if open_notebook:
                    args.append("--open-notebook")
                app_subprocess = subprocess.Popen(
                    args,
                    env=os.environ,
                    stdin=sys.stdin,
                    stdout=sys.stdout,
                    stderr=sys.stderr,
                )
                app_subprocess.wait()
            except (InterruptedError, KeyboardInterrupt, EOFError) as err:
                click.echo("y")
                click.echo("Shutting down...")
                break
    finally:
        if app_subprocess:
            click.echo("Cleaning up...")
            app_subprocess.terminate()
        observer.unschedule_all()
        observer.stop()
        del observer
