import click
import copy
import inspect
import os
import subprocess
import sys
import tempfile
import toml
import typing
from dataclasses import MISSING
from functools import partial

from dataclasses import dataclass, field, Field
from hatch.project.core import Project
from hatchling.builders.plugin.interface import BuilderInterface
from hatchling.metadata.utils import normalize_project_name

# Manual "import" of a static method as it acts like a normal function
normalize_file_name_component = BuilderInterface.normalize_file_name_component

from .helpers import find_pyproject_file

from beaker_kernel.lib.config import config


HATCH_NEW_SUBKERNEL_CONFIG_FILE_DEFAULTS = {
    'template': {
        'plugins': {
        },
    }
}

def resolve(field_name: str, options: dict[str, typing.Any], defaults: dict | None):
    field = SubkernelConfig.__dataclass_fields__.get(field_name, None)
    render_func = field.metadata["render"]

    result = None
    if field_name in options:
        result = options[field_name]
    else:
        default = None
        if isinstance(defaults, dict) and field_name in defaults:
            default = defaults[field_name]
        elif field.metadata["default_factory"] is not MISSING:
            default = field.metadata["default_factory"]()
        elif field.metadata["default"] is not MISSING:
            default = field.metadata["default"]

    if default is MISSING:
        default = None

    if default and callable(render_func):
        default = render_func(default, options=options, defaults=defaults)

    return result, default


def render_format(value: str, options: dict, defaults: dict | None):
    template_options = options.copy()
    if defaults:
        template_options.update({key: value for key, value in defaults.items() if key not in template_options})
    return value.format(**template_options)

def normalize_file_name_component(value: str, options: dict = None, defaults: dict | None = None):
    return BuilderInterface.normalize_file_name_component(value)

def render_class_name(value, options, defaults):
    value = render_format(value, options, defaults)
    value = normalize_project_name(value)
    return ''.join(word.capitalize() for word in value.split('-'))

def ConfigField(
        default: typing.Any = MISSING,
        default_factory: typing.Callable[[], typing.Any] = MISSING,
        description: str = MISSING,
        prompt: str = MISSING,
        default_default: typing.Any = MISSING,
        examples: list[typing.Any] = MISSING,
        render: typing.Callable[[str, dict[str, typing.Any], dict[str, typing.Any]], str] = MISSING,
        **kwargs,
):
    metadata = {
        "description": description,
        "prompt": prompt,
        "default_default": default_default,
        "examples": examples,
        "render": render,
        "default": default,
        "default_factory": default_factory,
    }
    return field(
        metadata=metadata,
        **kwargs,
    )

@dataclass
class SubkernelConfig():
    subkernel_slug: str = ConfigField(
        description="Slug for identifying the subkernel. Must be universally unique.",
        prompt="Slug for subkernel",
        default="{project_name}",
        render=lambda value, options, defaults: normalize_project_name(render_format(value, options, defaults)),
    )
    subkernel_display_name: str = ConfigField(
        description="",
        prompt="Display (human) name for subkernel",
        default="{project_name}",
        render=lambda value, options, defaults: " ".join(word.capitalize() for word in render_format(value, options, defaults).split('-')),
    )
    subkernel_class_name: str = ConfigField(
        description="",
        prompt="Subkernel class name",
        default="{project_name}-subkernel",
        render=render_class_name,
    )
    subkernel_subdirectory: str = ConfigField(
        description="",
        prompt="Subkernel location",
        default="{file_base}_subkernel",
        render=render_format,
    )
    kernel_name: str = ConfigField(
        description="",
        prompt="Name of kernel that this subkernel runs atop",
        examples=["ir", "ipython"],
    )
    kernel_package: str = ConfigField(
        description="",
        prompt="Name of package that contains the kernel",
        examples=["IRKernel", "IPython"],
    )



@click.group(name="subkernel")
def subkernel():
    """
    Commands for creating a new subkernel.
    """
    pass


@subkernel.command(name="new")
@click.argument(
    "name",
    required=False,
)
@click.option(
    "--class-base-name", "-c", "class_base_name",
    type=str,
    help="Base root name for generating classes such as the subclasses of BeakerContext and BeakerAgent.",
)
def new_subkernel(name, class_base_name):
    """
    Create a new subkernel.
    """
    pyproject_path = find_pyproject_file()
    if not pyproject_path:
        raise click.ClickException("You do not seem to be running within a valid project.")
    project = Project(pyproject_path)

    for project_name in (
        normalize_file_name_component(project.metadata.core.raw_name),
        normalize_file_name_component(project.metadata.core.name),
    ):
        project_source_path = project.root / project_name

        if (project_source_path / '__init__.py').is_file():
            break

        project_source_path = project.root / 'src' / project_name
        if (project_source_path / '__init__.py').is_file():
            break

    else:
        raise click.ClickException("You do not seem to be running within a valid project.")

    options = {}
    if name:
        options["project_name"] = normalize_project_name(name)
    if class_base_name:
        options["class_base_name"] = class_base_name
    options["file_base"] = normalize_file_name_component(options["project_name"])

    options = prompt_for_missing_new_subkernel_options(options)

    subkernel_target_dir = project_source_path / options["subkernel_subdirectory"]

    while (subkernel_target_dir / 'subkernel.py').exists():
        click.echo(f"Unable to write subkernel at location {subkernel_target_dir} as "
                   f"{subkernel_target_dir / 'subkernel.py'} already exists.")
        options["subkernel_subdirectory"] = click.prompt(
            "Sub-directory to write subkernel files",
            default=normalize_file_name_component(options["subkernel_name"]),
        )
        subkernel_target_dir = project_source_path / options["subkernel_subdirectory"]

    options['subkernel_target_dir'] = "."
    output_dir = str(subkernel_target_dir.relative_to(project_source_path))

    hatch_config = copy.deepcopy(HATCH_NEW_SUBKERNEL_CONFIG_FILE_DEFAULTS)
    # hatch_subkernel_config = {key.replace("_", "-"): value for key, value in options.items()}
    hatch_subkernel_config = {key.replace("-", "_"): value for key, value in options.items()}
    hatch_config['template']['plugins']['beaker-new-subkernel'] = hatch_subkernel_config

    # Execute hatch new to create the project
    args = [sys.executable, '-m', 'hatch', 'new', normalize_file_name_component(options["project_name"]), output_dir]
    environ = os.environ.copy()
    with tempfile.NamedTemporaryFile('w') as tempconfig:
        tempconfig.write(toml.dumps(hatch_config))
        tempconfig.flush()
        environ.update({
            "HATCH_CONFIG": tempconfig.name,
        })
        result = subprocess.run(
            args,
            env=environ,
            cwd=project_source_path,
        )
        if result.returncode > 0:
            raise click.ClickException("There was an error setting up your new Beaker project. Please check the output above.")


@click.option(
    "--all", "-a", "all",
    type=bool,
    is_flag=True,
    default=False,
    help="Show all subkernels, not just ones that are available."
)
@subkernel.command(name="list")
def list_subkernels(all):
    """
    List installed subkernels.

    Unless specified via the -all flag, only available subkernels will be displayed.
    Usually the reason why a subkernel will not be available is that a required kernel has not been installed in your
    current environment.

    Information on which kernels/packages are required to run a kernel is usually found in the docsting for a subkernel,
    viewable when run with the -a flag.
    """
    from beaker_kernel.lib.subkernel import autodiscover_subkernels
    # Fetch installed jupyter subkernels
    from jupyter_client.kernelspec import KernelSpecManager
    ksm = KernelSpecManager()
    kernel_specs = ksm.get_all_specs()
    kernel_languages = {
        spec.get("spec", {}).get("language")
        for spec in kernel_specs.values()
    }
    subkernels = {
        name: cls
        for name, cls in autodiscover_subkernels().items()
        if cls is not None and (
            all
            or getattr(cls, 'KERNEL_NAME', None) in kernel_specs
            or getattr(cls, 'JUPYTER_LANGUAGE', None) in kernel_languages
        )
    }
    if subkernels:
        click.echo("Currently installed subkernels:\n")
        for subkernel_name, subkernel_cls in subkernels.items():
            autodiscovery_data = getattr(subkernel_cls, '_autodiscovery', None)
            subkernel_doc = getattr(subkernel_cls, '__doc__', None)
            display_name = getattr(subkernel_cls, 'DISPLAY_NAME', subkernel_name.capitalize())
            kernel_name = getattr(subkernel_cls, 'KERNEL_NAME', 'undetermined') or 'undetermined'
            indent = 4
            output = [
                f"  {subkernel_name}{' ({})'.format(display_name)}:",
            ]
            if subkernel_doc:
                output.append(
                    f"{' ' * indent}'''" +
                    '\n'.join(
                        [
                            (
                                (' ' * indent) +
                                line
                            ) for line in subkernel_doc.splitlines()]
                    ) +
                    f"\n{' ' * indent}'''"
                )
            else:
                output.append(f"{' ' * indent}''' ( docstring not defined ) '''")
            output.extend([
                f"    Subkernel Class:           {subkernel_cls.__module__}.{subkernel_cls.__name__}",
                f"                                 ({inspect.getfile(subkernel_cls)})",
                f"    Display name:              {display_name}",
                f"    Jupyter kernel name:       {kernel_name}",
                f"    Jupyter kernel installed?: {str(kernel_name in kernel_specs).upper()}",
            ])
            if autodiscovery_data:
                output.append(
                    f"    Registration file:         {autodiscovery_data.get('mapping_file', 'unknown')}",
                )
            output.append("\n")
            click.echo("\n".join(output))
            click.echo("-" * 80)
    else:
        click.echo("No subkernels were found. Please check that you are running in the correct environment.")

def prompt_for_missing_new_subkernel_options(options: dict[str, any], defaults: dict[str, any] | None = None) -> dict[str, any]:
    if not defaults:
        defaults = {}
    data = {}
    for field_name, field_def in SubkernelConfig.__dataclass_fields__.items():
        value, default = resolve(field_name, options, defaults)
        if value:
            data[field_name] = value
        else:
            prompt_text = field_def.metadata["prompt"]
            value = click.prompt(prompt_text, default=default)
            options[field_name] = value
            data[field_name] = value

    return options
