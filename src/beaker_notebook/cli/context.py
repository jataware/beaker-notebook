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


HATCH_NEW_CONTEXT_CONFIG_FILE_DEFAULTS = {
    'template': {
        'plugins': {
        },
    }
}


@click.group(name="context")
def context():
    """
    Commands for creating a new context.
    """
    pass


@context.command(name="new")
@click.argument(
    "name",
    required=False,
)
@click.option(
    "--class-base-name", "-c", "class_base_name",
    type=str,
    help="Base root name for generating classes such as the subclasses of BeakerContext and BeakerAgent.",
)
@click.option(
    "--with-ui", "-u", "include_ui",
    type=bool,
    is_flag=True,
    default=False,
    help="Include UI scaffolding (renderers, components, pages).",
)
def new_context(name, class_base_name, include_ui):
    """
    Creates a new context in the current project.
    """
    from pathlib import Path

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
        options["context_name"] = normalize_project_name(name)
    if class_base_name:
        options["class_base_name"] = class_base_name

    options = prompt_for_missing_new_context_options(options)

    # UI scaffolding prompt
    if not include_ui:
        include_ui = click.confirm("Include UI scaffolding (renderers, components, pages)?", default=False)

    context_target_dir = project_source_path / options["context_subdirectory"]

    while (context_target_dir / 'context.py').exists() or (context_target_dir / 'agent.py').exists():
        click.echo(f"Unable to write context at location {context_target_dir} as {context_target_dir / 'context.py'} "
                   f"and/or {context_target_dir / 'agent.py'} already exist.")
        options["context_subdirectory"] = click.prompt(
            "Sub-directory to write context files",
            default=normalize_file_name_component(options["context_name"]),
        )
        context_target_dir = project_source_path / options["context_subdirectory"]

    options['context_target_dir'] = "."
    output_dir = str(context_target_dir.relative_to(project_source_path))

    hatch_config = copy.deepcopy(HATCH_NEW_CONTEXT_CONFIG_FILE_DEFAULTS)
    hatch_context_config = {key.replace("_", "-"): value for key, value in options.items()}
    hatch_config['template']['plugins']['beaker-new-context'] = hatch_context_config

    # Execute hatch new to create the project
    args = [sys.executable, '-m', 'hatch', 'new', options["context_name"], output_dir]
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

    if include_ui:
        _scaffold_ui_for_context(project.root, project_source_path, options["context_name"])


@context.command(name="dump")
@click.option(
    "--output", "-o",
    type=click.Path(),
    default=None,
    help="Output file path. Defaults to stdout.",
)
@click.option(
    "--context-slug", "-c", "context_slug",
    type=str,
    default=None,
    help="Filter to a specific context by slug.",
)
@click.option(
    "--package", "-p",
    type=str,
    default=None,
    help="Filter to a specific package by name.",
)
@click.option(
    "--compact",
    is_flag=True,
    default=False,
    help="Output compact JSON (no indentation).",
)
def dump_contexts(output, context_slug, package, compact):
    """
    Dump context metadata as JSON in the interchange format.

    Discovers installed contexts and extracts their integrations, workflows,
    and metadata into a JSON structure suitable for ingestion into BeakerHub.
    """
    from beaker_notebook.lib.context_dump import generate_context_dumps, dumps_to_json

    dumps = generate_context_dumps(
        context_filter=context_slug,
        package_filter=package,
    )

    if not dumps:
        raise click.ClickException(
            "No contexts found matching the given filters."
            if (context_slug or package)
            else "No contexts were found. Please check that you are running in the correct environment."
        )

    json_output = dumps_to_json(dumps, pretty=not compact)

    if output:
        with open(output, "w") as f:
            f.write(json_output)
            f.write("\n")
        click.echo(f"Wrote {len(dumps)} package dump(s) to {output}")
    else:
        click.echo(json_output)


@context.command(name="list")
def list_contexts():
    """
    List installed contexts.
    """
    from beaker_notebook.lib.context import autodiscover_contexts
    from beaker_notebook.lib import BeakerContext, BeakerAgent
    contexts = autodiscover_contexts()
    if contexts:
        click.echo("Currently installed contexts:\n")
        for context_name, context_cls in contexts.items():
            agent_cls = getattr(context_cls, 'agent_cls', None)
            context_doc = getattr(context_cls, '__doc__', None)
            indent = 4
            output = [
                f"  {context_name}:",
            ]
            if context_doc:
                output.append(
                    # f"    Context docstring:" +
                    f"{' ' * indent}'''\n" +
                    '\n'.join(
                        [
                            (
                                (' ' * indent) +
                                line
                            ) for line in context_doc.splitlines()]
                    ) +
                    f"\n{' ' * indent}'''"
                )
            else:
                output.append(f"{' ' * indent}''' ( docstring not defined ) '''")
            output.extend([
                f"    Context Class:   {context_cls.__module__}.{context_cls.__name__}",
                f"                       ({inspect.getfile(context_cls)})",
            ])
            if agent_cls:
                output.extend([
                f"    Agent Class:     {agent_cls.__module__}.{agent_cls.__name__}",
                f"                       ({inspect.getfile(agent_cls)})",
                # f"      File:            {inspect.getfile(agent_cls)}",

                ])
            output.append("")
            click.echo("\n".join(output))
    else:
        click.echo("No contexts were found. Please check that you are running in the correct environment.")


def _scaffold_ui_for_context(project_root, project_source_path, context_name: str):
    """
    Create package-level UI scaffolding (if not already present) and a context-level
    renderers.ts stub. Called after the Hatch template has created the context files.
    """
    from pathlib import Path

    ui_dir = project_root / "ui"
    pkg_slug = project_source_path.name
    assets_dir = project_source_path / "assets"

    # Compute the relative path from ui/ to the package's assets/ dir for vite outDir
    assets_relpath = os.path.relpath(assets_dir, ui_dir)

    # 1. Create package-level ui/ directory if it doesn't exist
    if not ui_dir.exists():
        click.echo("Creating package-level UI scaffolding...")

        # ui/package.json
        (ui_dir / "src").mkdir(parents=True, exist_ok=True)
        (ui_dir / "package.json").write_text(f"""\
{{
  "name": "{pkg_slug}-ui",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {{
    "build": "vite build",
    "dev": "vite build --watch"
  }},
  "dependencies": {{
    "@jataware/beaker-client": "*",
    "@jataware/beaker-vue": "*",
    "vue": "^3.4.0"
  }},
  "devDependencies": {{
    "@vitejs/plugin-vue": "^5.0.0",
    "@vitejs/plugin-vue-jsx": "^4.0.0",
    "typescript": "^5.5.0",
    "vite": "^6.0.0",
    "vite-plugin-css-injected-by-js": "^3.5.0"
  }}
}}
""")

        # ui/vite.config.ts
        # Use forward slashes for the path (vite/node convention)
        vite_out_dir = assets_relpath.replace(os.sep, "/") + "/"
        (ui_dir / "vite.config.ts").write_text(f"""\
import {{ defineBeakerRendererConfig }} from '@jataware/beaker-vue/build';

export default defineBeakerRendererConfig({{
    build: {{
        outDir: '{vite_out_dir}',
        lib: {{
            entry: {{
                "renderers": "./src/renderers.ts",
            }},
        }},
    }},
}});
""")

        # ui/tsconfig.json
        (ui_dir / "tsconfig.json").write_text("""\
{
  "extends": "@jataware/beaker-vue/tsconfig.renderers.json",
  "compilerOptions": {
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": [
    "src/**/*.ts",
    "src/**/*.tsx",
    "src/**/*.vue"
  ]
}
""")

        # ui/src/renderers.ts (package-level stub)
        (ui_dir / "src" / "renderers.ts").write_text("""\
import type { BeakerMimeRenderer } from '@jataware/beaker-vue';

// Package-level renderers.
// Export an array of BeakerMimeRenderer objects.
const renderers: BeakerMimeRenderer[] = [];
export default renderers;
""")

        # assets/.gitkeep (inside the package directory)
        assets_dir.mkdir(parents=True, exist_ok=True)
        (assets_dir / ".gitkeep").touch()

    # 2. Add PKG_SLUG and ASSET_DIR to package __init__.py if not present
    init_path = project_source_path / "__init__.py"
    if init_path.exists():
        init_contents = init_path.read_text()
        if "ASSET_DIR" not in init_contents:
            with open(init_path, "a") as f:
                f.write(f"""\
from pathlib import Path

PKG_SLUG = "{pkg_slug}"
ASSET_DIR = str(Path(__file__).parent / "assets")
""")

    # 3. Create context-level UI stub
    context_ui_dir = ui_dir / "src" / context_name
    if not context_ui_dir.exists():
        click.echo(f"Creating context-level UI stub for '{context_name}'...")
        context_ui_dir.mkdir(parents=True, exist_ok=True)
        (context_ui_dir / "renderers.ts").write_text(f"""\
import type {{ BeakerMimeRenderer }} from '@jataware/beaker-vue';

// Context-level renderers for '{context_name}'.
// Export an array of BeakerMimeRenderer objects.
const renderers: BeakerMimeRenderer[] = [];
export default renderers;
""")

    # 4. Add context entry to vite.config.ts if not already present
    vite_config_path = ui_dir / "vite.config.ts"
    if vite_config_path.exists():
        vite_contents = vite_config_path.read_text()
        context_entry = f'"{context_name}/renderers"'
        if context_entry not in vite_contents:
            # Insert the context entry point alongside the existing entries
            vite_contents = vite_contents.replace(
                '"renderers": "./src/renderers.ts",',
                f'"renderers": "./src/renderers.ts",\n                "{context_name}/renderers": "./src/{context_name}/renderers.ts",',
            )
            vite_config_path.write_text(vite_contents)


def prompt_for_missing_new_context_options(options: dict[str, any], defaults: dict[str, any] | None = None) -> dict[str, any]:
    if not defaults:
        defaults = {}

    if "context_name" not in options:
        options["context_name"] = click.prompt("Name for the context", default=defaults.get("context_name", None))
    if "class_base_name" not in options:
        class_base_name_default_base: str = defaults.get("class_base_name", options["context_name"])
        class_base_name_default = ''.join(word.capitalize() for word in class_base_name_default_base.split('-'))
        options["class_base_name"] = click.prompt("Base Name for generated classes", default=class_base_name_default)
    if "context_subdirectory" not in options:
        options["context_subdirectory"] = click.prompt(
            "Sub-directory to write context files",
            default=normalize_file_name_component(defaults.get("context_subdirectory", options["context_name"])),
        )

    return options
