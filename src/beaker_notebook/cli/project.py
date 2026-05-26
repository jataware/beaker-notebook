import click
import copy
import importlib
import json
import os
import re
import subprocess
import sys
import tempfile
import toml
from importlib.metadata import distribution, PackageNotFoundError
from pathlib import Path

from hatch.project.core import Project
from hatchling.builders.config import BuilderConfig
from hatchling.metadata.utils import normalize_project_name

from .helpers import find_pyproject_file, find_pyproject_dir


HATCH_NEW_PROJECT_CONFIG_FILE_DEFAULTS = {
    'template': {
        'plugins': {
            'default': {},
            'beaker-new-project': {},
        },
    }
}

@click.group(name="project")
def project():
    """
    Beaker project management
    """
    pass

@project.command(name="new")
@click.argument(
    "name",
    required=False,
)
@click.option(
    "--no-interaction", "-n", "no_interact",
    type=bool,
    is_flag=True,
    default=False,
    help="Do not prompt for any information. Will fail if `name` is not provided."
)
@click.option(
    "--dependency", "-d", "dependencies",
    multiple=True,
    help="A dependency to include in the pyproject. Example: 'pandas>=3.2.0'"
)
@click.option(
    "--no-context", "-c", "no_context",
    type=bool,
    is_flag=True,
    default=False,
    help="Do not include a sample context."
)
@click.pass_context
def new_project(ctx: click.Context, name, no_interact, dependencies, no_context):
    """
    Creates a new Beaker Python project.

    This project can add new context(s) and/or subkernels to Beaker as an additional Python library.

    NAME is used for both the generated directory and project name in pyproject.toml. The convention is to split words
    with dashes (-) instead of underscores or using CamelCase.
    If NAME is not provided you will be prompted, unless --no-interaction.
    """
    # Perform import in action to prevent possible circular import
    from . import context

    dependencies = list(dependencies)

    normalized_name = None
    while not name or not normalized_name:
        if name:
            normalized_name = normalize_project_name(re.sub(r'\s', '.', name))
            if name != normalized_name:
                if not no_interact:
                    click.echo(
                        "PEP-503 (https://peps.python.org/pep-0503/#normalized-names) suggests normalization of "
                        "package names.")
                    if click.confirm(f"Use normalized name '{normalized_name}' instead?", default=True):
                        name = normalized_name
                        continue
                else:
                    click.echo(
                        f"Notice: package name '{name}' does not confirm to the normalization defined in PEP-503 "
                        "(https://peps.python.org/pep-0503/#normalized-names).\n"
                        "However proceeding with provided name since --no-interaction flag has been set."
                    )
            if re.search(r'\s', name):
                if not no_interact:
                    click.echo(f"Name cannot contain whitespace ('{name}' entered).")
                    name = None
                    normalized_name = None
                    continue
                else:
                    raise click.ClickException(f"Name cannot contain whitespace ('{name}' entered).")
        else:
            if not no_interact:
                while not name:
                    name = click.prompt("Project name")
            else:
                raise click.ClickException("A name is a required argument when the --no-interaction flag is set.")
        project_path: Path = Path.cwd() / name
        if (project_path.exists() and not project_path.is_dir()) or (project_path.is_dir() and os.listdir(project_path)):
            click.echo(f"Notice: {project_path.absolute()} exists and is not an empty directory.\n        Please "
                       "select a different project name or change working directories.")
            name = None
            normalized_name = None

    # Additional dependencies
    if not no_interact:
        if click.confirm("Would you like to provide additional dependencies now?", default=False):
            click.echo("Leave blank to finish.")
            while dependency := click.prompt("Dependency definition", default="", show_default=False):
                dependencies.append(dependency)

    if not no_context:
        if no_interact:
            class_base_name_default = ''.join(word.capitalize() for word in normalized_name.split('-'))
            context_config = {
                "context_name": normalized_name,
                "class_base_name": class_base_name_default,
            }
        else:
            if click.confirm("Would you like to include an example context?", default=True):
                context_config = context.prompt_for_missing_new_context_options(
                    {},
                    defaults={
                        "context_name": name,
                        "context_subdirectory": f"{name}_context",
                    }
                )
                context_config['context_target_dir'] = "{package_name}/{context_subdir}"
            else:
                context_config = {}
    else:
        context_config = {}

    click.echo("\nGenerating project files...")
    # Define hatch config
    hatch_config = copy.deepcopy(HATCH_NEW_PROJECT_CONFIG_FILE_DEFAULTS)
    project_config = hatch_config['template']['plugins']['beaker-new-project']
    project_config['package-name'] = name
    project_config['dependencies'] = dependencies
    if context_config:
        hatch_context_config = {key.replace("_", "-"): value for key, value in context_config.items()}
        hatch_config['template']['plugins']['beaker-new-context'] = hatch_context_config

    # Execute hatch new to create the project
    args = [sys.executable, '-m', 'hatch', 'new', name]
    environ = os.environ.copy()
    with tempfile.NamedTemporaryFile('w') as tempconfig:
        tempconfig.write(toml.dumps(hatch_config))
        tempconfig.flush()
        environ.update({
            "HATCH_CONFIG": tempconfig.name,
        })
        result = subprocess.call(args, env=environ)
        if result > 0:
            raise click.ClickException("There was an error setting up your new Beaker project. Please check the output above.")
    click.echo("Done.\n")

    if not no_interact:
        if click.confirm("Would you like to install the new project in dev mode in your current environment?", default=False):
            click.echo("")
            ctx.invoke(update, path=(Path.cwd() / name))
        click.echo("")

    click.echo( "Note:")
    click.echo( "  Some changes, such as adding or moving a context require updating/reinstalling the project.")
    click.echo(f"  You may need to run 'beaker project update' if you encounter issues after making updates to the project.")


# @project.command()
# @click.option(
#     "-e", "--editable", "editable",
#     is_flag=True,
#     default=False,
#     help='Install the project in editable mode (i.e. setuptools "develop mode").',
# )
# @click.argument("path", required=False, default=None, type=click.Path(path_type=Path))
# def install(path):
#     """
#     Installs a project
#     """
#     pyproject_path = find_pyproject_file(path)
#     if not pyproject_path:
#         search_path = path.absolute() if path else Path.cwd()
#         raise click.ClickException(f"{search_path} does not appear to be part of a valid project.")
#     project = Project(pyproject_path)
#     click.echo(f"Reinstalling {project.metadata.core.name} from directory {project.root}")
#     subprocess.call(
#         args=[sys.executable, '-m', 'pip', 'install', '-e', '.'],
#         env=os.environ,
#         cwd=project.root,
#     )


@project.command()
@click.argument("path", required=False, default=None, type=click.Path(path_type=Path))
def update(path):
    """
    (Re)installs the project in editable mode ("develop mode") in the current python environment.

    """
    pyproject_path = find_pyproject_file(path)
    if not pyproject_path:
        search_path = path.absolute() if path else Path.cwd()
        raise click.ClickException(f"{search_path} does not appear to be part of a valid project.")
    project = Project(pyproject_path)
    click.echo(f"Reinstalling {project.metadata.core.name} from directory {Path(project.root).absolute()}")
    subprocess.call(
        args=[sys.executable, '-m', 'pip', 'install', '-e', '.'],
        env=os.environ,
        cwd=project.root,
    )


@project.command()
@click.argument("project_name_or_path", required=False, default=None)
def info(project_name_or_path):
    """
    Information about a project. Looks for a project in current location if no project name is provided.
    """
    from beaker_kernel.lib import BeakerContext, BeakerSubkernel
    from beaker_kernel.builder.beaker import BeakerBuildHook
    from hatchling.builders.wheel import WheelBuilderConfig, WheelBuilder
    project_info = None
    # Case if project is not yet installed or is running against unpublished modifications
    if project_name_or_path is None or os.path.isdir(project_name_or_path) or os.path.isfile(project_name_or_path):
        pyproject_file = find_pyproject_file(project_name_or_path)
        project_dir = pyproject_file.parent.absolute()
        if pyproject_file:
            project = Project(pyproject_file)
            project_name = project.metadata.core.name
            build_config = WheelBuilderConfig(
                WheelBuilder(
                    root=project_dir,
                    config=project.config,
                    metadata=project.metadata,

                ),
                project_dir,
                project_name,
                project.config.config["build"],
                target_config={}
            )
            builder = BeakerBuildHook(
                directory=project_dir,
                root=project_dir,
                config=project.config,
                build_config=build_config,
                metadata=project.metadata,
                target_name="wheel"
            )
            builder.add_packages_to_path()
            contexts = builder.find_slugged_subclasses_of(BeakerContext)
            subkernels = builder.find_slugged_subclasses_of(BeakerSubkernel)
            description = project.metadata.core.description
            urls = [f"{key}: {value}" for key, value in project.metadata.core.urls.items()]
            project_info = {
                "name": project_name,
                "urls": urls,
                "description": description,
                "contexts": contexts,
                "subkernels": subkernels,
            }

    # Case if has been installed and is being analyzed from the site-lib packages dir
    if project_info is None:
        pyproject_file = None
        project_dir = None
        project_name = ""
        try:
            dist = distribution(project_name_or_path)
            project_name = dist.name
            project_description = dist.metadata.get("summary")
            contexts = {}
            subkernels = {}
            for file in dist.files:
                if "/share/beaker/contexts/" in str(file):
                    content = json.loads(file.read_text())
                    contexts[content['slug']] = (content['package'], content['class_name'])
                elif "/share/beaker/subkernels/" in str(file):
                    content = json.loads(file.read_text())
                    subkernels[content['slug']] = (content['package'], content['class_name'])
            project_info = {
                "name": dist.name,
                "urls": dist.metadata.get_all("project-url"),
                "description": project_description,
                "contexts": contexts,
                "subkernels": subkernels,
            }
        except PackageNotFoundError:
            project_info = None

    if project_info is None:
        raise click.ClickException(
            f"The provided value '{project_name_or_path}' does not appear to exist or to be installed.\n"
            f"       If this is a path to a local project, please ensure the path is correct.\n"
            f"       If this is the name of a project, please ensure that it is installed in the current Python environment."
        )

    click.echo(f"Project {project_info['name']}:")
    click.echo(f"  Description:\n    {project_info['description']}")

    if project_info.get("urls", None):
        click.echo(f"  Urls:")
        for url in project_info['urls']:
            url = url.replace(',', ':', 1)
            click.echo(f"    {url}")

    if contexts:
        click.echo(f"\n  Contexts:")
        for context_slug, (mod_name, cls_name) in contexts.items():
            mod = importlib.import_module(mod_name)
            cls: type = getattr(mod, cls_name)
            click.echo( f"    {context_slug}:")
            if cls.__doc__:
                click.echo('      """')

                click.echo("\n".join(f"       {line}" for line in cls.__doc__.strip().splitlines(False)))
                click.echo('      """')
    if subkernels:
        click.echo(f"\n\n  Subkernels:")
        for subkernel_slug, (mod_name, cls_name) in subkernels.items():
            mod = importlib.import_module(mod_name)
            cls: type = getattr(mod, cls_name)
            click.echo(f"    {subkernel_slug}:")
            if cls.__doc__:
                click.echo('      """')

                click.echo("\n".join(f"       {line}" for line in cls.__doc__.strip().splitlines(False)))
                click.echo('      """')
