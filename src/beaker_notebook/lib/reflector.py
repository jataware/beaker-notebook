"""
Reflector registry and discovery.

A reflector is a procedure that produces a structured description of a runtime
value in a subkernel's language. Each reflector targets a specific language
+ type and contributes a function (in the subkernel's language) that the
``fetch_state`` template composes into a dispatch block.

Reflectors are discovered as Jinja-templated files under
``<procedures_root>/reflectors/<typename>.<ext>``. Each file declares its
metadata via Jinja-comment headers at the top of the file:

    {# target_type: pandas.DataFrame #}
    {# function_name: _beaker_reflect_dataframe #}
    def _beaker_reflect_dataframe(_value):
        ...

The header is stripped at render time so it never reaches the subkernel.

The agent-facing ``describe_variables`` tool surfaces a richer reflection on
demand. The dispatch chain reads: ReflectorRegistry -> render fetch_state ->
language code calls reflector function -> VariableDescription -> agent.
"""

import logging
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Optional

from jinja2 import Environment, Template, TemplateNotFound

logger = logging.getLogger(__name__)

# Matches a Jinja comment block at the top of a file (ignoring leading
# whitespace). Header parsing only consumes leading consecutive comment
# blocks; once any non-whitespace, non-comment content appears, parsing stops.
_LEADING_COMMENT_RE = re.compile(r"\s*\{#\s*(.*?)\s*#\}", re.DOTALL)

# Required header keys for a reflector file.
REQUIRED_HEADER_KEYS: tuple[str, ...] = ("target_type", "function_name")

# Default priority when a reflector header omits it. Higher = checked earlier.
DEFAULT_PRIORITY = 100

# Path prefix (within a procedures root) under which reflectors live.
REFLECTOR_SUBDIR = "reflectors"


@dataclass
class Reflector:
    """A single reflector: language + target type(s) + function-name + template."""

    name: str
    """Slug derived from the reflector filename (no extension, no dirs)."""

    target_types: tuple[str, ...]
    """Language-native type identifier(s) the reflector matches against. The
    ``target_type`` header value may be a single identifier or a comma-
    separated list; both forms are normalized into this tuple at load time."""

    function_name: str
    """Name of the function defined inside the rendered template body."""

    template: Template
    """The Jinja template object, ready to render."""

    priority: int
    """Dispatch priority. Higher values are matched earlier in fetch_state's
    type-dispatch block. Default ``DEFAULT_PRIORITY`` (100); a fallback
    reflector typically uses 0 or negative."""

    metadata: dict[str, str]
    """All header key/value pairs, including required and any extras."""


class ReflectorRegistry(Mapping[str, Reflector]):
    """Mapping of reflector name -> Reflector, with iteration order preserved.

    Mirrors the pattern of IntegrationProviderRegistry / WorkflowRegistry.
    Insertion order is the registration order, which is the order the
    ``fetch_state`` template will dispatch through. Earlier registrations win
    on duplicate names (so context-level reflectors registered first override
    subkernel-level defaults registered second).
    """

    def __init__(self, reflectors: Optional[list[Reflector]] = None):
        self._by_name: dict[str, Reflector] = {}
        if reflectors:
            for reflector in reflectors:
                self.add(reflector)

    def add(self, reflector: Reflector) -> None:
        if reflector.name in self._by_name:
            # First registration wins; later duplicates are ignored.
            logger.debug(
                "Reflector %r already registered; ignoring duplicate.",
                reflector.name,
            )
            return
        self._by_name[reflector.name] = reflector

    def __getitem__(self, name: str) -> Reflector:
        return self._by_name[name]

    def __iter__(self) -> Iterator[str]:
        return iter(self._by_name)

    def in_dispatch_order(self) -> list[Reflector]:
        """Return reflectors sorted by priority (descending), then name
        (ascending) for stable tiebreaks. This is the order the fetch_state
        template should emit dispatch arms in.
        """
        return sorted(
            self._by_name.values(),
            key=lambda r: (-r.priority, r.name),
        )

    def __len__(self) -> int:
        return len(self._by_name)

    def __bool__(self) -> bool:
        return bool(self._by_name)

    @property
    def by_target_type(self) -> dict[str, Reflector]:
        """Reverse lookup keyed by each declared target type. A reflector that
        declares multiple ``target_types`` appears under each key."""
        result: dict[str, Reflector] = {}
        for reflector in self._by_name.values():
            for target in reflector.target_types:
                # First registration of a given target wins, mirroring the
                # registry's "first add wins" policy.
                result.setdefault(target, reflector)
        return result

    @classmethod
    def from_jinja_env(
        cls,
        env: Environment,
        subdir: str = REFLECTOR_SUBDIR,
    ) -> "ReflectorRegistry":
        """Build a registry by scanning ``env`` for templates under ``subdir/``.

        Header parse failures and missing required keys are logged and the
        offending file is skipped. The CLI ``beaker subkernel verify`` command
        is the loud-failure path; runtime is lenient.
        """
        registry = cls()
        loader = env.loader
        if loader is None:
            return registry

        prefix = f"{subdir}/"
        for template_path in env.list_templates():
            if not template_path.startswith(prefix):
                continue
            basename = template_path[len(prefix):].rsplit("/", 1)[-1]
            if basename.startswith("__") or basename.startswith("."):
                continue

            name = template_path[len(prefix):].rsplit(".", 1)[0]
            try:
                source, _, _ = loader.get_source(env, template_path)
            except (TemplateNotFound, UnicodeDecodeError) as err:
                logger.warning(
                    "Skipping reflector %r: cannot read source (%s).",
                    template_path,
                    err,
                )
                continue

            header = parse_reflector_header(source)
            missing = [k for k in REQUIRED_HEADER_KEYS if k not in header]
            if missing:
                logger.warning(
                    "Skipping reflector %r: missing required header keys %s.",
                    template_path,
                    missing,
                )
                continue

            try:
                template = env.get_template(template_path)
            except Exception as err:
                logger.warning(
                    "Skipping reflector %r: template parse failed (%s).",
                    template_path,
                    err,
                )
                continue

            try:
                priority = int(header.get("priority", DEFAULT_PRIORITY))
            except ValueError:
                logger.warning(
                    "Reflector %r has non-integer priority %r; using default.",
                    template_path,
                    header.get("priority"),
                )
                priority = DEFAULT_PRIORITY

            target_types = tuple(
                t.strip() for t in header["target_type"].split(",") if t.strip()
            )
            if not target_types:
                logger.warning(
                    "Skipping reflector %r: empty target_type after parsing.",
                    template_path,
                )
                continue

            registry.add(
                Reflector(
                    name=name,
                    target_types=target_types,
                    function_name=header["function_name"],
                    template=template,
                    priority=priority,
                    metadata=header,
                )
            )
        return registry


def parse_reflector_header(source: str) -> dict[str, str]:
    """Extract ``key: value`` pairs from leading Jinja comment blocks.

    Multiple consecutive ``{# ... #}`` blocks are accumulated. Blank lines and
    lines without a colon are ignored. Parsing stops at the first non-comment
    content (after skipping leading whitespace).
    """
    metadata: dict[str, str] = {}
    pos = 0
    while True:
        match = _LEADING_COMMENT_RE.match(source, pos)
        if not match:
            break
        block = match.group(1)
        for line in block.splitlines():
            line = line.strip()
            if not line or ":" not in line:
                continue
            key, _, value = line.partition(":")
            metadata[key.strip()] = value.strip()
        pos = match.end()
    return metadata
