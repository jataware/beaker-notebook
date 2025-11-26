import importlib
import inspect
import os
import toml
from collections import deque
from dataclasses import MISSING, is_dataclass
from pathlib import Path
from typing import Mapping, Sequence, Any, get_origin, get_args

import click

from beaker_kernel.lib.config import locate_config, config, ConfigClass, Table, recursiveOptionalUpdate, Choice
from beaker_kernel.lib.utils import import_dotted_class


SENSITIVE_STR_REPR = "*" * 8

def indent(amount):
    return "  " * amount

def terse_print(obj: Any, indent_level=1):
    if isinstance(obj, Mapping):
        for varname, value in obj.items():
            should_indent = isinstance(value, (Mapping, list))
            sep = ":" if should_indent else "="
            click.echo(f"{indent(indent_level)}{varname}{sep}", nl=should_indent)
            terse_print(value, indent_level=indent_level+1)
    elif isinstance(obj, list):
        for value in obj:
            terse_print(value, indent_level=indent_level+1)
    else:
        click.echo(obj)

@click.group(name="config")
def config_group():
    """
    Options for viewing and updating configuration settings
    """
    pass


@config_group.command()
def find():
    """
    Locate the configuration file for currently in use
    """
    config_file = locate_config()
    if os.path.isfile(config_file):
        click.echo(f"Configuration location: {config_file}\n")
    else:
        click.echo(f"No configuration file located.\nDefault location is: {config_file}\n")


def _print_config_obj(obj, sensitive=False, obj_type=None, metadata=None, indent_level=0):
    from typing import get_origin, get_args
    description: str = metadata is not None and metadata.get("description", None)
    if obj_type is None:
        obj_type = obj.__class__
    if is_dataclass(obj) or (is_dataclass(obj_type) and obj is not None):
        if description:
            click.echo(f"\n{indent(indent_level)}# {description}")
        indent_level += 1
        for field_name, field in obj_type.__dataclass_fields__.items():
            metadata = field.metadata
            aliases: list[str] = field.metadata.get("aliases", None) or []

            if is_dataclass(obj):
                value = getattr(obj, field_name)
            else:
                value = obj.get(field_name)

            vars_to_check = [field_name, *aliases]
            for config_name in vars_to_check:
                if config_name in obj:
                    obj.pop(config_name)
                    break

            click.echo(f"{indent(indent_level)}{field_name}: ", nl=False)
            _print_config_obj(value, sensitive=sensitive, obj_type=field.type, metadata=metadata, indent_level=indent_level + 1)
    elif isinstance(obj, Table) or (get_origin(obj_type) is not None and issubclass(get_origin(obj_type), Table) and obj is not None):
        if description:
            click.echo(f"\n{indent(indent_level)}# {description}")
        for key, value in obj.items():
            click.echo(f"{indent(indent_level)}{key}: ", nl=True)
            _print_config_obj(value, sensitive=sensitive, obj_type=get_args(obj_type)[0], indent_level=indent_level+1)
    else:
        if description:
            click.echo(f"{indent(indent_level)}# {description}")
        is_sensitive: bool = metadata is not None and metadata.get("sensitive", False) or False
        if is_sensitive and not sensitive:
            if obj:
                display_value = SENSITIVE_STR_REPR  # rerun with -s flag to display value
            else:
                display_value = '(undefined)'
        elif isinstance(obj, str) and obj == "":
            display_value = '"" (empty string)'
        else:
            display_value = obj
        click.echo(f"{indent(indent_level)}{display_value}")


def _update_config_obj(config_data, label=None, sensitive=False, obj_type=None, metadata=None, indent_level=0, default=None, save_default_value=False):
    description: str = metadata is not None and metadata.get("description", None)

    if obj_type is None:
        obj_type = config_data.__class__

    if is_dataclass(obj_type):
        if not isinstance(config_data, dict):
            config_data = {}
        result = {}
        if label:
            click.echo(f"\n\n{indent(indent_level)}# {label}:")
        indent_level += 1
        queue = deque(obj_type.__dataclass_fields__.items())
        while queue:
            field_name, field = queue.popleft()
            if (isinstance(default, dict) or is_dataclass(default)) and field_name in default:
                field_default = default.get(field_name)
            elif field.default is not MISSING:
                field_default = field.default
            elif field.default_factory is not MISSING:
                field_default = field.default_factory()
            else:
                field_default = MISSING
            field_value = _update_config_obj(
                config_data=config_data.get(field_name, None),
                label=field_name,
                sensitive=field.metadata.get("sensitive", False),
                obj_type=field.type,
                metadata=field.metadata,
                indent_level=indent_level,
                default=field_default,
            )

            if field_value != MISSING:
                result[field_name] = field_value
        # Do not save/overwrite empty/unchanged tables.
        if not len(result):
            return MISSING
        return result

    elif isinstance(config_data, Table) or (get_origin(obj_type) is not None and issubclass(get_origin(obj_type), Table)):
        click.echo(f"\n\n{indent(indent_level)}# {label}  -  {description}")
        result = {}
        keys = []
        if not isinstance(metadata, Mapping):
            metadata = {}
        if not config_data or not isinstance(config_data, (dict, Table)):
            if default is None or default is MISSING:
                default = {}
            config_data = {}
            keys.extend(default.keys())
        else:
            keys += [key for key in config_data.keys() if key not in keys]

        for key in keys:
            record_value = _update_config_obj(
                config_data=config_data.get(key, None),
                label=key,
                sensitive=sensitive,
                obj_type=get_args(obj_type)[0],
                metadata={
                    "save_default_value": metadata.get('save_default_value', False),
                    "description": metadata.get('label', None),
                },
                indent_level=indent_level+1,
                default=default.get(key, {})
            )
            if record_value is not MISSING:
                result[key] = record_value
        # Do not save/overwrite empty/unchanged tables.
        if not len(result):
            return MISSING
        return result
    else:
        description = metadata.get("description", "(No description provided)")
        is_sensitive = metadata.get("sensitive", False)
        save_default_value = metadata.get("save_default_value", False)
        if config_data:
            default = config_data

        if is_sensitive and default:
            default_display = SENSITIVE_STR_REPR
        else:
            default_display = default

        choices = None
        prompt_type = None
        value_proc = None
        if "options" in metadata:
            choices = metadata.get("options")()
            prompt_type = click.Choice(choices.keys())
            def value_proc(choice):
                result = choices.get(choice, MISSING)
                if result is MISSING:
                    raise click.UsageError(f"'{choice}' is not a valid option. Please select from the list above.")
                return result
            if default_display in choices.values():
                default_display = {value: key for key, value in choices.items()}.get(default_display, None)

        prompt = f"""
{indent(indent_level)}{label} --
{indent(indent_level+1)}Description: {description}
{indent(indent_level+1)}{label}"""

        value = click.prompt(prompt, default=default_display, type=prompt_type, value_proc=value_proc)
        was_value_entered = value != default_display

        # Empty value is considered equal to a config_data of None
        is_value_different = ((not (config_data is None and value == "")) and (value != config_data))
        if was_value_entered and is_value_different:
            return value
        elif save_default_value and config_data is None:
            return default
        else:
            return MISSING


@config_group.command()
@click.option("--sensitive", "-s", is_flag=True, default=False, type=bool, help="By default, sensitive values are masked. Set this flag to show the actual value.")
def show(sensitive):
    """
    Displays the current Beaker configuration
    """
    config_file: Path|None = locate_config()
    if config_file and config_file.exists():
        config_data = toml.loads(config_file.read_text())
    else:
        config_data = {}

    click.echo(f"Current Beaker configuration:")
    _print_config_obj(config_data, sensitive=sensitive, obj_type=ConfigClass, indent_level=0)

    if not sensitive:
        click.echo("\n# To expose sensitive values, rerun with the -s flag")


@config_group.command()
@click.option("--file", "-f", "config_file", type=click.Path(exists=False))
def update(config_file: str):
    """
    Iterate through available options, prompting for new or updated values.
    """
    if config_file is None:
        config_file = locate_config()
    else:
        config_file = Path(config_file)

    if config_file.exists():
        config_data = toml.loads(config_file.read_text())
    else:
        config_data = {}

    updates = _update_config_obj(config_data, label=f"Updating Beaker config ({config_file})", sensitive=False, obj_type=ConfigClass, indent_level=0)

    if updates and updates is not MISSING:
        click.echo("\n\n-------------\nUpdated values:")
        terse_print(updates)

        approval = click.prompt(f"Save above values to file {config_file}?", default="y", type=bool)
        if isinstance(approval, bool) and approval:
            click.echo("Saving...")
            updated_config: dict = recursiveOptionalUpdate(config, updates, remove_missing=False)
            config.update(updated_config, config_file)
            click.echo("Done.")
        else:
            click.echo("Aborting without saving.")
    else:
        click.echo("No updates detected.")
