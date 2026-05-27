import importlib
import inspect
import pkgutil
import subprocess
import sys
import tempfile
from pathlib import Path

import click
import psutil

from beaker_kernel import app
from beaker_kernel.app.base import BaseBeakerApp


TEMP_DIR = Path(tempfile.gettempdir())


@click.group(name="server")
def server():
    """
    Options for finding, configuring, and running Beaker Servers
    """
    pass


@server.command()
def list_types():
    """
    List all available Beaker server types.
    """
    app_types = []

    # Find all modules in beaker_kernel.app package
    for finder, name, ispkg in pkgutil.iter_modules(app.__path__, app.__name__ + "."):
        if not ispkg:  # Only include modules, not subpackages
            module_name = name.split('.')[-1]  # Get just the module name
            # Skip internal modules
            if not module_name.startswith('_') and module_name not in ['handlers', 'admin_utils']:
                app_types.append(module_name)

    click.echo("Available Beaker server types:")
    for app_type in sorted(app_types):
        click.echo(f"  {app_type}")


@server.command(context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
@click.argument("server_type", type=click.STRING, default="server")
@click.option("--force", is_flag=True, help="Force start even if server is already running")
@click.option("--port", type=int, default=8888, help="Port to run server on")
@click.option("--daemon", "-d", is_flag=True, help="Run server in daemon mode")
@click.pass_context
def start(ctx, server_type, force, port, daemon):
    """
    Start a Beaker Server instance
    """
    # Check if server is already running
    pidfile = TEMP_DIR / f"beaker_{server_type}_{port}.pid"

    if pidfile.exists() and not force:
        try:
            with open(pidfile) as f:
                pid = int(f.read().strip())
            if psutil.pid_exists(pid):
                proc = psutil.Process(pid)
                if any('beaker_kernel.app' in ' '.join(cmd) for cmd in [proc.cmdline()]):
                    click.echo(f"Beaker {server_type} server is already running on port {port} (PID: {pid})")
                    click.echo("Use --force to start anyway")
                    return
        except (ValueError, FileNotFoundError, psutil.NoSuchProcess):
            # PID file exists but process is not running, remove stale pidfile
            pidfile.unlink(missing_ok=True)

    # Build command
    cmd = [sys.executable, "-m", f"beaker_kernel.app.{server_type}_app", "--port", str(port)]

    # Add any extra arguments from ctx.args
    if ctx.args:
        cmd.extend(ctx.args)

    click.echo(f"Starting Beaker {server_type} server on port {port}...")

    if daemon:
        # Start in daemon mode
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

        # Save PID to file
        with open(pidfile, 'w') as f:
            f.write(str(proc.pid))

        click.echo(f"Server started in daemon mode (PID: {proc.pid})")
    else:
        # Start in foreground
        try:
            proc = subprocess.Popen(cmd)
            # Save PID to file
            with open(pidfile, 'w') as f:
                f.write(str(proc.pid))

            # Wait for process
            proc.wait()
        except KeyboardInterrupt:
            click.echo("\nShutting down server...")
            proc.terminate()
            proc.wait()
        finally:
            # Clean up PID file
            pidfile.unlink(missing_ok=True)


@server.command(context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
@click.argument("server_type", type=click.STRING, default="server")
@click.option("--port", type=int, default=8888, help="Port the server is running on")
@click.option("--all", "stop_all", is_flag=True, help="Stop all Beaker servers")
@click.pass_context
def stop(ctx, server_type, port, stop_all):
    """
    Stop a Beaker Server instance
    """
    if stop_all:
        # Stop all beaker servers
        pidfiles = list(TEMP_DIR.glob("beaker_*.pid"))
        stopped_count = 0

        for pidfile in pidfiles:
            try:
                with open(pidfile) as f:
                    pid = int(f.read().strip())

                if psutil.pid_exists(pid):
                    proc = psutil.Process(pid)
                    if any('beaker_kernel.app' in ' '.join(cmd) for cmd in [proc.cmdline()]):
                        click.echo(f"Stopping Beaker server (PID: {pid})...")
                        proc.terminate()
                        try:
                            proc.wait(timeout=10)
                        except psutil.TimeoutExpired:
                            proc.kill()
                        stopped_count += 1

                pidfile.unlink(missing_ok=True)
            except (ValueError, FileNotFoundError, psutil.NoSuchProcess) as e:
                pidfile.unlink(missing_ok=True)

        if stopped_count > 0:
            click.echo(f"Stopped {stopped_count} Beaker server(s)")
        else:
            click.echo("No running Beaker servers found")
        return

    # Stop specific server
    pidfile = TEMP_DIR / f"beaker_{server_type}_{port}.pid"

    if not pidfile.exists():
        click.echo(f"No Beaker {server_type} server running on port {port}")
        return

    try:
        with open(pidfile) as f:
            pid = int(f.read().strip())

        if psutil.pid_exists(pid):
            proc = psutil.Process(pid)
            if any('beaker_kernel.app' in ' '.join(cmd) for cmd in [proc.cmdline()]):
                click.echo(f"Stopping Beaker {server_type} server (PID: {pid})...")
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                    click.echo("Server stopped")
                except psutil.TimeoutExpired:
                    click.echo("Server did not stop gracefully, killing...")
                    proc.kill()
                    click.echo("Server killed")
            else:
                click.echo(f"PID {pid} is not a Beaker server process")
        else:
            click.echo(f"Process {pid} is not running")

        pidfile.unlink(missing_ok=True)
    except (ValueError, FileNotFoundError, psutil.NoSuchProcess) as e:
        click.echo(f"Error stopping server: {e}")
        pidfile.unlink(missing_ok=True)


@server.command()
@click.option("--file", "-f", "config_file", type=click.Path(exists=False))
@click.argument("server_type", type=click.STRING, default="")
def generate_config(server_type=None, config_file=None):
    """
    Generate a server configuration file with all available options.
    """
    app_class: type[BaseBeakerApp]
    if server_type:
        app_mod_str: str = f"beaker_kernel.app.{server_type}_app"
        app_module = importlib.import_module(app_mod_str)
        app_classes = inspect.getmembers(app_module, lambda obj: isinstance(obj, type) and issubclass(obj, BaseBeakerApp) and obj != BaseBeakerApp)
        if app_classes:
            _, app_class = app_classes[0]
        else:
            raise LookupError("Unable to determine intended BeakerAppClass")
        if not config_file:
            config_file = f"beaker_{app_class._app_slug()}_config.py"
    else:
        app_class = BaseBeakerApp
        if not config_file:
            config_file = "beaker_config.py"

    app: BaseBeakerApp = app_class(config_file=config_file)
    app.initialize(argv=[])
    app.write_default_config()
