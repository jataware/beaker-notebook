from hatch.template import File
from hatch.utils.fs import Path
from pathlib import Path
import typing
from typing import Any, ClassVar

import jinja2
from jinja2 import Template


class PathTemplate:
    def __init__(self, template: str, condition=None) -> None:
        self.template = template
        self.condition = condition

    def render(self, template_values) -> str:
        return self.template.format(**template_values)


PathPart: typing.TypeAlias = PathTemplate | str


class TemplateFile(File):
    PATH_PARTS: ClassVar[list[PathPart]]
    TEMPLATE: ClassVar[str]
    path_parts: list[PathPart]
    template: str
    path_prefix: Path | str | None
    relative_to: Path | str | None

    def __init__(
            self,
            path_parts: list[PathPart] | None = None,
            template: str | None = None,
            path_prefix: Path | str | None = None,
            relative_to: Path | str | None = None,
        ):
        self.path_parts = path_parts or self.PATH_PARTS
        self.template = template or self.TEMPLATE
        self.path_prefix = path_prefix or None
        self.relative_to = relative_to

    def render_path(self, template_config: dict, plugin_config: dict):
        template_values = template_config.copy()
        template_values.update(plugin_config)

        parts = []
        for part in [self.path_prefix] + self.path_parts:
            if part is None:
                continue
            if isinstance(part, PathTemplate):
                if part.condition and not part.condition(template_values):
                    continue
                parts.append(part.render(template_values))
            else:
                try:
                    rendered_part = str(part).format(**template_values)
                except:
                    rendered_part = str(part)
                parts.append(rendered_part)
        path = Path(*parts)
        if self.relative_to and path.is_relative_to(self.relative_to):
            path = path.relative_to(self.relative_to)
        return path

    def render(self, **template_mapping: dict[str, Any]) -> str:
        return self.template.format(**template_mapping)

    def write(self, root):
        return super().write(root)

    def __call__(self, template_config: dict, plugin_config: dict) -> Any:
        path = self.render_path(template_config, plugin_config)
        contents = self.render(**template_config)
        super().__init__(path, contents)
        return self


class JinjaTemplateFile(TemplateFile):
    def render(self, **template_mapping: dict[str, Any]) -> str:
        t = jinja2.Template(self.template)
        contents = t.render(**template_mapping)
        return contents


class InitFile(TemplateFile):
    PATH_PARTS = ['__init__.py']
    TEMPLATE = ""  # Empty file

    def __init__(
            self,
            path_parts: list[PathPart] | None = None,
            template: str | None = None,
            path_prefix: Path | str | None = None,
            relative_to: Path | str | None = None,
        ):
        super().__init__(path_parts=path_parts, template=template, path_prefix=path_prefix, relative_to=relative_to)
        if not self.path_parts[-1] == '__init__.py':
            self.path_parts.append('__init__.py')

    def write(self, root):
        path: Path = root / self.path
        # Only write an __init__.py file if it doesn't already exist.
        if not path.is_file():
            return super().write(root)
