from hatch.template.plugin.interface import TemplateInterface
from hatch.template.files_default import PyProject, PackageRoot, Readme as HatchReadme

from beaker_notebook.lib.templates import InitFile
from beaker_notebook.lib.templates.paths import package_name
from beaker_notebook.lib.templates.agent_file import AgentFile
from beaker_notebook.lib.templates.context_file import ContextFile
from beaker_notebook.lib.templates.readme_file import ReadmeFile
from beaker_notebook.lib.templates.procedure_file import ProcedureFile
from beaker_notebook.lib.templates.subkernel_file import SubkernelFile
from beaker_notebook.lib.templates.ui_files import (
    UIPackageJsonFile, UIViteConfigFile, UITsConfigFile, UIRenderersFile,
    UIContextRenderersFile, UIAssetsGitkeepFile,
)

class BeakerNewProjectTemplateHook(TemplateInterface):
    PLUGIN_NAME = 'beaker-new-project'
    PRIORITY = 200  # Run after 'default' which has priority 100

    def initialize_config(self, config):
        """
        Allow modification of the configuration passed to every file for new projects
        before the list of files are determined.
        """
        from importlib.metadata import version
        extra_dependencies = self.plugin_config.get("dependencies", [])

        config["dependencies"].add(f"beaker_notebook~={version('beaker_notebook')}")
        if extra_dependencies:
            config["dependencies"].update(extra_dependencies)

        config["include_ui"] = self.plugin_config.get("include-ui", False)
        config["include_context_ui"] = self.plugin_config.get("include-context-ui", False)

    def get_files(self, config):
        files = [
            ReadmeFile(),
        ]
        if config.get("include_ui"):
            files.extend([
                UIPackageJsonFile(),
                UIViteConfigFile(),
                UITsConfigFile(),
                UIRenderersFile(),
                UIAssetsGitkeepFile(),
            ])
            if config.get("include_context_ui") and config.get("context_name"):
                files.append(UIContextRenderersFile())
        return files

    def finalize_files(self, config: dict, files: list):
        """Allow modification of files for new projects before they are written to the file system."""
        # Locate the PyProject file created by the 'default' plugin and add to the bottom of it before writing.
        file_map = {type(f): f for f in files}
        pyproject_file = file_map.get(PyProject, None)

        # Append beaker specific configuration to pyproject.
        if pyproject_file:
            pyproject_file.contents += """\n
[tool.hatch.build.hooks.beaker]
require-runtime-dependencies = true

"""

        # If include_ui is set, add PKG_SLUG and ASSET_DIR to the package __init__.py
        if config.get("include_ui"):
            package_root_file = file_map.get(PackageRoot, None)
            if package_root_file:
                pkg_slug = config.get("package_name", "")
                package_root_file.contents += f'''\
from pathlib import Path

PKG_SLUG = "{pkg_slug}"
ASSET_DIR = str(Path(__file__).parent / "assets")
'''

        # If context-specific UI is enabled, add the context entry to vite.config.ts
        if config.get("include_context_ui") and config.get("context_name"):
            vite_file = file_map.get(UIViteConfigFile, None)
            if vite_file:
                context_name = config["context_name"]
                vite_file.contents = vite_file.contents.replace(
                    '"renderers": "./src/renderers.ts",',
                    f'"renderers": "./src/renderers.ts",\n                "{context_name}/renderers": "./src/{context_name}/renderers.ts",',
                )

        # If we have both the default Hatch readme file and the Beaker readme file, remove the Hatch version of the file
        if HatchReadme in file_map and ReadmeFile in file_map:
            files.remove(file_map.get(HatchReadme))


class BeakerNewContextTemplateHook(TemplateInterface):
    PLUGIN_NAME = 'beaker-new-context'
    PRIORITY = 250  # Run after 'default' which has priority 100

    def initialize_config(self, config):
        """
        Allow modification of the configuration passed to every file for new projects
        before the list of files are determined.
        """
        class_base = self.plugin_config["class-base-name"]
        context_subdir = self.plugin_config.get("context-subdirectory", None)
        config["context_subdir"] = context_subdir
        config["context_name"] = self.plugin_config["context-name"]
        config["context_class"] = f"{class_base}Context"
        config["agent_class"] = f"{class_base}Agent"
        config["context_target_dir"] = self.plugin_config.get("context-target-dir", package_name)


    def get_files(self, config: dict):
        """Add to the list of files for new projects that are written to the file system."""
        files = [
            ContextFile(path_prefix=config.get("context_target_dir")),
            AgentFile(path_prefix=config.get("context_target_dir")),
            InitFile(path_prefix=config.get("context_target_dir")),
            ProcedureFile(path_prefix=config.get("context_target_dir")),
        ]
        return files


class BeakerNewSubkernelTemplateHook(TemplateInterface):
    PLUGIN_NAME = 'beaker-new-subkernel'
    PRIORITY = 250  # Run after 'default' which has priority 100

    def initialize_config(self, config):
        """
        Allow modification of the configuration passed to every file for new projects
        before the list of files are determined.
        """
        config.update({key: value for key, value in self.plugin_config.items() if key not in config})


    def get_files(self, config: dict):
        """Add to the list of files for new projects that are written to the file system."""
        files = [
            SubkernelFile(),
        ]
        return files


