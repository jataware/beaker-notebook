"""
Validates the ``beaker_kernel`` -> ``beaker_notebook`` compatibility shim.

When the package was renamed, ``src/beaker_kernel/__init__.py`` installed a
meta-path finder that redirects every ``beaker_kernel[.X]`` import to the
matching ``beaker_notebook[.X]`` module (see that file for the mechanism).

This used to be guarded by keeping a full, byte-for-byte copy of the test
suite that imported through the old names. That copy was a maintenance burden:
every real test change had to be mirrored here. Instead, we only assert the one
thing the shim is responsible for -- that each old import name resolves to the
*same module object* as its new name (and therefore the same file on disk).

The loader does ``sys.modules[old] = importlib.import_module(new)``, so the old
and new module are literally the same object; identity is the strongest check
available and implies ``__file__`` points at the real ``beaker_notebook`` source.

``SHIMMED_MODULES`` lists every old-name module the surrounding code/tests
import, with the public symbols they rely on. Add an entry here when new code
starts depending on a ``beaker_kernel.*`` import.
"""

import importlib
import os

import pytest

import beaker_notebook

_OLD = "beaker_kernel"
_NEW = "beaker_notebook"

# Root of the real (new) package on disk; every shimmed module's file must live
# under here.
_PKG_DIR = os.path.dirname(os.path.abspath(beaker_notebook.__file__))


# Old-name module -> public symbols that dependent code imports from it.
SHIMMED_MODULES: dict[str, tuple[str, ...]] = {
    "beaker_kernel.builder.hooks": ("hatch_register_template",),
    "beaker_kernel.cli.subkernel": ("verify_subkernel",),
    "beaker_kernel.contexts.default.agent": ("DefaultAgent",),
    "beaker_kernel.lib": ("subkernel",),
    "beaker_kernel.lib.agent": ("BeakerAgent",),
    "beaker_kernel.lib.code_analysis": ("AnalysisASTRule",),
    "beaker_kernel.lib.code_analysis.analysis_agent": ("AnalysisAgent", "AnalysisResult"),
    "beaker_kernel.lib.code_analysis.analysis_types": ("AnalysisCodeCell", "AnalysisCodeCells"),
    "beaker_kernel.lib.code_analysis.analyzer": ("AnalysisEngine",),
    "beaker_kernel.lib.code_analysis.rules.trust.categories": (
        "literal_value_issue",
        "trust_assumptions_category",
        "trust_grounding_category",
    ),
    "beaker_kernel.lib.code_analysis.rules.trust.rules": (
        "all_rules",
        "ast_rules",
        "llm_rules",
        "trust_literal_check_filter",
    ),
    "beaker_kernel.lib.context": ("BeakerContext",),
    "beaker_kernel.lib.integrations.adhoc": ("AdhocIntegrationProvider",),
    "beaker_kernel.lib.integrations.skill": (
        "SkillIntegrationProvider",
        "extract_file_references",
        "find_resource_dirs",
        "parse_example_md",
        "parse_skill_md",
    ),
    "beaker_kernel.lib.integrations.types": (
        "SkillExampleResource",
        "SkillFileResource",
        "SkillInstructionsResource",
        "SkillIntegration",
        "SkillMetadataResource",
    ),
    "beaker_kernel.lib.kernel_state": ("apply_sample_budget", "render_agent_payload"),
    "beaker_kernel.lib.reflector": (
        "DEFAULT_PRIORITY",
        "REFLECTOR_SUBDIR",
        "Reflector",
        "ReflectorRegistry",
        "parse_reflector_header",
    ),
    "beaker_kernel.lib.subkernel": ("BeakerSubkernel", "autodiscover_subkernels"),
    "beaker_kernel.lib.templates.agent_file": ("AgentFile",),
    "beaker_kernel.lib.templates.context_file": ("ContextFile",),
    "beaker_kernel.lib.templates.procedure_file": ("ProcedureFile",),
    "beaker_kernel.lib.templates.readme_file": ("ReadmeFile",),
    "beaker_kernel.lib.templates.subkernel_file": ("SubkernelFile",),
    "beaker_kernel.lib.utils": ("ExecutionError", "normalize_notebook"),
    "beaker_kernel.lib.workflow": (
        "Workflow",
        "WorkflowRegistry",
        "WorkflowStage",
        "WorkflowStageProgress",
        "WorkflowStep",
        "workflow_condition",
    ),
}

# Old-name modules that intentionally do NOT exist anymore. The shim must not
# fabricate them: importing should still raise. (The whitelabel template was
# removed during the rename.)
REMOVED_MODULES: tuple[str, ...] = (
    "beaker_kernel.lib.templates.whitelabel_file",
)


def _new_name(old_name: str) -> str:
    return _NEW + old_name[len(_OLD):]


def test_top_level_alias_is_new_package():
    """``import beaker_kernel`` yields the ``beaker_notebook`` package itself."""
    old = importlib.import_module(_OLD)
    assert old is beaker_notebook


@pytest.mark.parametrize("old_name", sorted(SHIMMED_MODULES), ids=sorted(SHIMMED_MODULES))
def test_shim_resolves_to_same_module(old_name):
    """The old name resolves to the exact same module object as the new name."""
    old_mod = importlib.import_module(old_name)
    new_mod = importlib.import_module(_new_name(old_name))
    assert old_mod is new_mod, (
        f"{old_name} should be aliased to {_new_name(old_name)} "
        f"but resolved to {getattr(old_mod, '__file__', old_mod)!r}"
    )


@pytest.mark.parametrize("old_name", sorted(SHIMMED_MODULES), ids=sorted(SHIMMED_MODULES))
def test_shim_module_file_lives_in_new_package(old_name):
    """Introspect ``__file__``: the backing source is under ``beaker_notebook/``."""
    mod = importlib.import_module(old_name)
    mod_file = getattr(mod, "__file__", None)
    assert mod_file is not None, f"{old_name} has no __file__ to introspect"
    mod_file = os.path.abspath(mod_file)
    assert mod_file.startswith(_PKG_DIR + os.sep), (
        f"{old_name} is backed by {mod_file}, expected a file under {_PKG_DIR}"
    )
    # The renamed package must not be served out of an old-name directory.
    parts = mod_file.split(os.sep)
    assert _OLD not in parts, f"{old_name} resolves through a '{_OLD}' directory: {mod_file}"


@pytest.mark.parametrize("old_name", sorted(SHIMMED_MODULES), ids=sorted(SHIMMED_MODULES))
def test_shim_module_exposes_expected_symbols(old_name):
    """The symbols dependent code imports through the old name are present."""
    mod = importlib.import_module(old_name)
    missing = [name for name in SHIMMED_MODULES[old_name] if not hasattr(mod, name)]
    assert not missing, f"{old_name} is missing expected symbols: {missing}"


@pytest.mark.parametrize("old_name", REMOVED_MODULES, ids=REMOVED_MODULES)
def test_removed_module_is_not_shimmed(old_name):
    """The shim must not invent modules that no longer exist on the new side."""
    with pytest.raises(ImportError):
        importlib.import_module(old_name)
