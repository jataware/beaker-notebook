"""
Tests for scaffolding templates in beaker_notebook.lib.templates.

These tests render each template with sample values and validate:
- The rendered output is syntactically valid Python
- Imports reference modules that actually exist
- The super().__init__() calls match the current base class signatures
- Class variables match what the base classes expect
"""

import ast
import importlib
import inspect
import textwrap
from typing import Any

import pytest

from beaker_notebook.lib.templates.context_file import ContextFile
from beaker_notebook.lib.templates.agent_file import AgentFile
from beaker_notebook.lib.templates.subkernel_file import SubkernelFile
from beaker_notebook.lib.templates.procedure_file import ProcedureFile
from beaker_notebook.lib.templates.readme_file import ReadmeFile

from beaker_notebook.lib.context import BeakerContext
from beaker_notebook.lib.agent import BeakerAgent
from beaker_notebook.lib.subkernel import BeakerSubkernel


# -- Fixtures for sample template values --

CONTEXT_TEMPLATE_VALUES = {
    "context_class": "TestExampleContext",
    "agent_class": "TestExampleAgent",
    "context_name": "test-example",
}

AGENT_TEMPLATE_VALUES = {
    "agent_class": "TestExampleAgent",
}

SUBKERNEL_TEMPLATE_VALUES = {
    "subkernel_class_name": "TestExampleSubkernel",
    "subkernel_display_name": "Test Example",
    "subkernel_slug": "test-example",
    "kernel_name": "python3",
    "kernel_package": "IPython",
}

README_TEMPLATE_VALUES = {
    "project_name": "test-example-project",
    "project_name_normalized": "test_example_project",
}


# -- Rendering helpers --

def render_template(template_cls, template_values: dict[str, Any]) -> str:
    """Instantiate a template class and render its content."""
    instance = template_cls()
    return instance.render(**template_values)


# -- Syntax validation tests --

class TestContextTemplate:
    def test_renders_valid_python(self):
        source = render_template(ContextFile, CONTEXT_TEMPLATE_VALUES)
        tree = ast.parse(source)
        assert isinstance(tree, ast.Module)

    def test_contains_context_class(self):
        source = render_template(ContextFile, CONTEXT_TEMPLATE_VALUES)
        tree = ast.parse(source)
        class_defs = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
        class_names = [cls.name for cls in class_defs]
        assert "TestExampleContext" in class_names

    def test_inherits_from_beaker_context(self):
        source = render_template(ContextFile, CONTEXT_TEMPLATE_VALUES)
        tree = ast.parse(source)
        class_def = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and node.name == "TestExampleContext"
        )
        base_names = [
            base.attr if isinstance(base, ast.Attribute) else base.id
            for base in class_def.bases
        ]
        assert "BeakerContext" in base_names

    def test_has_agent_cls_class_variable(self):
        source = render_template(ContextFile, CONTEXT_TEMPLATE_VALUES)
        tree = ast.parse(source)
        class_def = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and node.name == "TestExampleContext"
        )
        # Look for AGENT_CLS assignment in class body
        assigns = [
            node for node in class_def.body
            if isinstance(node, ast.Assign)
        ]
        assigned_names = []
        for assign in assigns:
            for target in assign.targets:
                if isinstance(target, ast.Name):
                    assigned_names.append(target.id)
        assert "AGENT_CLS" in assigned_names

    def test_has_slug_class_variable(self):
        source = render_template(ContextFile, CONTEXT_TEMPLATE_VALUES)
        tree = ast.parse(source)
        class_def = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and node.name == "TestExampleContext"
        )
        assigns = [
            node for node in class_def.body
            if isinstance(node, ast.Assign)
        ]
        assigned_names = []
        for assign in assigns:
            for target in assign.targets:
                if isinstance(target, ast.Name):
                    assigned_names.append(target.id)
        assert "SLUG" in assigned_names

    def test_super_init_matches_base_signature(self):
        """Verify the template's super().__init__() call is compatible with BeakerContext.__init__."""
        base_sig = inspect.signature(BeakerContext.__init__)
        base_params = list(base_sig.parameters.keys())
        # BeakerContext.__init__ expects: self, beaker_kernel, agent_cls, config, integrations=None
        assert "beaker_kernel" in base_params
        assert "agent_cls" in base_params
        assert "config" in base_params

        # Verify template calls super().__init__ with the right number of positional args
        source = render_template(ContextFile, CONTEXT_TEMPLATE_VALUES)
        tree = ast.parse(source)
        init_method = None
        class_def = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and node.name == "TestExampleContext"
        )
        for node in class_def.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "__init__":
                init_method = node
                break
        assert init_method is not None, "Template must define __init__"

        # Find the super().__init__() call
        super_call = None
        for node in ast.walk(init_method):
            if isinstance(node, ast.Call):
                func = node.func
                if (isinstance(func, ast.Attribute) and func.attr == "__init__"
                        and isinstance(func.value, ast.Call)
                        and isinstance(func.value.func, ast.Name)
                        and func.value.func.id == "super"):
                    super_call = node
                    break
        assert super_call is not None, "Template __init__ must call super().__init__()"

        # Count positional args in the super().__init__() call
        n_positional = len(super_call.args)
        # Should pass: beaker_kernel, self.AGENT_CLS, config (3 positional)
        required_base_params = [
            p for p in base_sig.parameters.values()
            if p.name != "self" and p.default is inspect.Parameter.empty
        ]
        assert n_positional == len(required_base_params), (
            f"Template super().__init__() passes {n_positional} positional args, "
            f"but BeakerContext.__init__ has {len(required_base_params)} required params: "
            f"{[p.name for p in required_base_params]}"
        )

    def test_imports_are_resolvable(self):
        """Verify that non-relative top-level imports in the rendered template reference real modules."""
        source = render_template(ContextFile, CONTEXT_TEMPLATE_VALUES)
        tree = ast.parse(source)
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    importlib.import_module(alias.name)
            elif isinstance(node, ast.ImportFrom):
                # Skip relative imports (level > 0) and TYPE_CHECKING blocks
                if node.level > 0:
                    continue
                if node.module:
                    importlib.import_module(node.module)


class TestAgentTemplate:
    def test_renders_valid_python(self):
        source = render_template(AgentFile, AGENT_TEMPLATE_VALUES)
        tree = ast.parse(source)
        assert isinstance(tree, ast.Module)

    def test_contains_agent_class(self):
        source = render_template(AgentFile, AGENT_TEMPLATE_VALUES)
        tree = ast.parse(source)
        class_defs = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
        class_names = [cls.name for cls in class_defs]
        assert "TestExampleAgent" in class_names

    def test_inherits_from_beaker_agent(self):
        source = render_template(AgentFile, AGENT_TEMPLATE_VALUES)
        tree = ast.parse(source)
        class_def = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and node.name == "TestExampleAgent"
        )
        base_names = [
            base.attr if isinstance(base, ast.Attribute) else base.id
            for base in class_def.bases
        ]
        assert "BeakerAgent" in base_names

    def test_has_tool_decorated_method(self):
        source = render_template(AgentFile, AGENT_TEMPLATE_VALUES)
        tree = ast.parse(source)
        class_def = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and node.name == "TestExampleAgent"
        )
        tool_methods = []
        for node in class_def.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    dec_name = None
                    if isinstance(decorator, ast.Call):
                        if isinstance(decorator.func, ast.Name):
                            dec_name = decorator.func.id
                    elif isinstance(decorator, ast.Name):
                        dec_name = decorator.id
                    if dec_name == "tool":
                        tool_methods.append(node.name)
        assert len(tool_methods) > 0, "Agent template should include at least one @tool() method"

    def test_no_unused_imports(self):
        """Verify the template doesn't import symbols it doesn't use."""
        source = render_template(AgentFile, AGENT_TEMPLATE_VALUES)
        tree = ast.parse(source)

        # Collect all imported names (skip TYPE_CHECKING block)
        imported_names = set()
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    name = alias.asname or alias.name
                    imported_names.add(name)

        # Collect all names used in the source (excluding imports themselves)
        used_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Store):
                used_names.add(node.id)

        # Imports under TYPE_CHECKING are exempt
        type_checking_imports = set()
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.If):
                test = node.test
                if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
                    for child in ast.walk(node):
                        if isinstance(child, ast.ImportFrom):
                            for alias in child.names:
                                type_checking_imports.add(alias.asname or alias.name)

        non_tc_imports = imported_names - type_checking_imports
        unused = non_tc_imports - used_names
        assert not unused, f"Template has unused imports: {unused}"

    def test_imports_are_resolvable(self):
        source = render_template(AgentFile, AGENT_TEMPLATE_VALUES)
        tree = ast.parse(source)
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    importlib.import_module(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module and not node.module.startswith("."):
                    importlib.import_module(node.module)


class TestSubkernelTemplate:
    def test_renders_valid_python(self):
        source = render_template(SubkernelFile, SUBKERNEL_TEMPLATE_VALUES)
        tree = ast.parse(source)
        assert isinstance(tree, ast.Module)

    def test_contains_subkernel_class(self):
        source = render_template(SubkernelFile, SUBKERNEL_TEMPLATE_VALUES)
        tree = ast.parse(source)
        class_defs = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
        class_names = [cls.name for cls in class_defs]
        assert "TestExampleSubkernel" in class_names

    def test_inherits_from_beaker_subkernel(self):
        source = render_template(SubkernelFile, SUBKERNEL_TEMPLATE_VALUES)
        tree = ast.parse(source)
        class_def = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and node.name == "TestExampleSubkernel"
        )
        base_names = [
            base.attr if isinstance(base, ast.Attribute) else base.id
            for base in class_def.bases
        ]
        assert "BeakerSubkernel" in base_names

    def test_has_required_class_variables(self):
        source = render_template(SubkernelFile, SUBKERNEL_TEMPLATE_VALUES)
        tree = ast.parse(source)
        class_def = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and node.name == "TestExampleSubkernel"
        )
        assigns = []
        for node in class_def.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        assigns.append(target.id)
        assert "DISPLAY_NAME" in assigns
        assert "SLUG" in assigns
        assert "KERNEL_NAME" in assigns
        assert "WEIGHT" in assigns

    def test_has_parse_subkernel_return(self):
        source = render_template(SubkernelFile, SUBKERNEL_TEMPLATE_VALUES)
        tree = ast.parse(source)
        class_def = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and node.name == "TestExampleSubkernel"
        )
        method_names = [
            node.name for node in class_def.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        assert "parse_subkernel_return" in method_names

    def test_import_path_uses_beaker_notebook_lib(self):
        """Verify the template imports BeakerSubkernel from beaker_notebook.lib, not beaker_notebook.lib.base."""
        source = render_template(SubkernelFile, SUBKERNEL_TEMPLATE_VALUES)
        tree = ast.parse(source)
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == "BeakerSubkernel":
                        assert node.module == "beaker_notebook.lib", (
                            f"BeakerSubkernel should be imported from beaker_notebook.lib, "
                            f"not {node.module}"
                        )

    def test_imports_are_resolvable(self):
        source = render_template(SubkernelFile, SUBKERNEL_TEMPLATE_VALUES)
        tree = ast.parse(source)
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    importlib.import_module(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module and not node.module.startswith("."):
                    importlib.import_module(node.module)


class TestProcedureTemplate:
    def test_renders_valid_python(self):
        source = render_template(ProcedureFile, {})
        tree = ast.parse(source)
        assert isinstance(tree, ast.Module)

    def test_output_path_is_under_procedures_python3(self):
        instance = ProcedureFile()
        assert instance.PATH_PARTS == ['procedures', 'python3', 'example.py']


class TestReadmeTemplate:
    def test_renders_without_error(self):
        content = render_template(ReadmeFile, README_TEMPLATE_VALUES)
        assert isinstance(content, str)
        assert len(content) > 0

    def test_contains_project_name(self):
        content = render_template(ReadmeFile, README_TEMPLATE_VALUES)
        assert "test-example-project" in content

    def test_contains_normalized_project_name(self):
        content = render_template(ReadmeFile, README_TEMPLATE_VALUES)
        assert "test_example_project" in content

    def test_contains_install_instructions(self):
        content = render_template(ReadmeFile, README_TEMPLATE_VALUES)
        assert "pip install" in content
        assert "beaker project update" in content


class TestWhiteLabelTemplateRemoved:
    """Verify that the whitelabel template has been fully removed."""

    def test_whitelabel_file_does_not_exist(self):
        with pytest.raises(ImportError):
            from beaker_notebook.lib.templates.whitelabel_file import WhiteLabelFile  # noqa: F401

    def test_whitelabel_hook_not_registered(self):
        from beaker_notebook.builder.hooks import hatch_register_template
        hooks = hatch_register_template()
        hook_names = [h.PLUGIN_NAME for h in hooks]
        assert "beaker-new-whitelabel" not in hook_names


class TestBaseClassCompatibility:
    """
    Tests that verify the templates stay in sync with base class signatures.
    If a base class changes its __init__ signature, these tests should break.
    """

    def test_context_init_param_names(self):
        """Guard against BeakerContext.__init__ signature changes."""
        sig = inspect.signature(BeakerContext.__init__)
        param_names = list(sig.parameters.keys())
        # If this assertion fails, the context template likely needs updating
        assert param_names == ["self", "beaker_kernel", "agent_cls", "config", "integrations"], (
            f"BeakerContext.__init__ signature changed: {param_names}. "
            f"Update the context template to match."
        )

    def test_agent_inherits_react_agent(self):
        """Guard against BeakerAgent base class changes."""
        from archytas.react import ReActAgent
        assert issubclass(BeakerAgent, ReActAgent)

    def test_subkernel_required_class_vars(self):
        """Verify the class variables the template sets are still recognized by BeakerSubkernel."""
        expected_vars = {"DISPLAY_NAME", "SLUG", "KERNEL_NAME", "WEIGHT"}
        # Some vars are annotations-only (no default), others have defaults and appear in dir()
        all_known = set(dir(BeakerSubkernel)) | set(BeakerSubkernel.__annotations__.keys())
        for var in expected_vars:
            assert var in all_known, (
                f"BeakerSubkernel no longer has {var}. "
                f"Update the subkernel template."
            )
