import click
import copy
import inspect
import os
import subprocess
import sys
import tempfile
import toml
from hatch.project.core import Project
from hatchling.builders.plugin.interface import BuilderInterface
from hatchling.metadata.utils import normalize_project_name

# Manual "import" of a static method as it acts like a normal function
normalize_file_name_component = BuilderInterface.normalize_file_name_component

from .helpers import find_pyproject_file
from .running import notebook


HATCH_NEW_CONTEXT_CONFIG_FILE_DEFAULTS = {
    'template': {
        'plugins': {
        },
    }
}


def build_app_command(app_name, import_str):
    @click.pass_context
    def inner(ctx: click.Context):
        os.environ.setdefault("BEAKER_APP", import_str)
        ctx.forward(notebook)
    return click.Command(name=app_name, callback=inner, help=f"""Beaker app '{app_name}' ({import_str}).""")


@click.group(name="app")
def app():
    """
    Commands for dealing with stand-alone/white-labeled apps.
    """
    pass


# @app.command(name="enable")
# # @click.option(
# #     "--class-base-name", "-c", "class_base_name",
# #     type=str,
# #     help="Base root name for generating classes such as the subclasses of BeakerContext and BeakerAgent.",
# # )
# def enable_app():
#     """
#     Ena
#     """
#     pyproject_path = find_pyproject_file()
#     if not pyproject_path:
#         raise click.ClickException("You do not seem to be running within a valid project.")
#     project = Project(pyproject_path)

#     for project_name in (
#         normalize_file_name_component(project.metadata.core.raw_name),
#         normalize_file_name_component(project.metadata.core.name),
#     ):
#         project_source_path = project.root / project_name

#         if (project_source_path / '__init__.py').is_file():
#             break

#         project_source_path = project.root / 'src' / project_name
#         if (project_source_path / '__init__.py').is_file():
#             break

#     else:
#         raise click.ClickException("You do not seem to be running within a valid project.")

#     options = {}
#     if name:
#         options["context_name"] = normalize_project_name(name)
#     if class_base_name:
#         options["class_base_name"] = class_base_name

#     options = prompt_for_missing_new_context_options(options)

#     context_target_dir = project_source_path / options["context_subdirectory"]

#     while (context_target_dir / 'context.py').exists() or (context_target_dir / 'agent.py').exists():
#         click.echo(f"Unable to write context at location {context_target_dir} as {context_target_dir / 'context.py'} "
#                    f"and/or {context_target_dir / 'agent.py'} already exist.")
#         options["context_subdirectory"] = click.prompt(
#             "Sub-directory to write context files",
#             default=normalize_file_name_component(options["context_name"]),
#         )
#         context_target_dir = project_source_path / options["context_subdirectory"]

#     options['context_target_dir'] = "."
#     output_dir = str(context_target_dir.relative_to(project_source_path))

#     hatch_config = copy.deepcopy(HATCH_NEW_CONTEXT_CONFIG_FILE_DEFAULTS)
#     hatch_context_config = {key.replace("_", "-"): value for key, value in options.items()}
#     hatch_config['template']['plugins']['beaker-new-context'] = hatch_context_config

#     # Execute hatch new to create the project
#     args = [sys.executable, '-m', 'hatch', 'new', options["context_name"], output_dir]
#     environ = os.environ.copy()
#     with tempfile.NamedTemporaryFile('w') as tempconfig:
#         tempconfig.write(toml.dumps(hatch_config))
#         tempconfig.flush()
#         environ.update({
#             "HATCH_CONFIG": tempconfig.name,
#         })
#         result = subprocess.run(
#             args,
#             env=environ,
#             cwd=project_source_path,
#         )
#         if result.returncode > 0:
#             raise click.ClickException("There was an error setting up your new Beaker project. Please check the output above.")


@app.command(name="list")
def list_apps():
    """
    List installed apps.
    """
    from beaker_kernel.lib.autodiscovery import autodiscover
    apps = autodiscover("apps")
    if apps:
        click.echo("Currently installed apps:\n")
        for app_name, app_cls in apps.items():
            click.echo(f"  {app_name}: {app_cls}\n")
    else:
        click.echo("No apps were found. Please check that you are running in the correct environment.")
