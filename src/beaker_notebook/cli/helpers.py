import click
import dotenv
import hashlib
import sys
from pathlib import Path
from functools import wraps

from beaker_kernel.lib.config import locate_envfile, locate_config, reset_config

def find_file_along_path(filename: str, start_path: Path | str | None = None) -> Path | None:
    if start_path is None:
        path = Path.cwd()
    else:
        path = Path(start_path)
    for search_path in [path, *path.parents]:
        potential_file = search_path / filename
        if potential_file.is_file():
            return potential_file
    return None


def find_pyproject_file(path: Path | str | None = None) -> Path | None:
    return find_file_along_path("pyproject.toml", path)


def find_pyproject_dir(path: Path | str | None = None) -> Path | None:
    return find_pyproject_file(path=path).parent.absolute()


def calculate_content_hash(
    content: str,
    hash_algo: str = "sha256"
) -> str:
    if isinstance(content, str):
        content = content.encode()
    hash_obj = hashlib.new(hash_algo, data=content)
    return str(hash_obj.hexdigest())


def ensure_config(fn):
    @wraps(fn)
    def _inner(*args, **kwargs):
        # Import update inside wrapping function to prevent circular imports. Could fail in outer file and in top-level
        # decorator.
        from .config import update

        ctx = click.get_current_context()

        if not locate_config().exists():
            timeout = 5
            import signal
            class Skip(Exception): pass
            def raise_e(*arg, **kwarg):
                click.echo("n")
                raise Skip()
            handler = signal.signal(signal.SIGALRM, raise_e)
            print(f"handler: {handler}")

            build_config = False
            try:
                signal.alarm(timeout)
                build_config = click.confirm(f"Looks like you haven't created a configuration yet. Would you like to create one now? (Timeout: {timeout} secs)", default=True)
            except Skip:
                pass
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, signal.SIG_DFL)

            if build_config:
                sys.stdout.flush()
                ctx.invoke(update)
                # Ensure config is reset before running function, to ensure that we don't use the default values.
                reset_config()

        fn(*args, **kwargs)

    return _inner
