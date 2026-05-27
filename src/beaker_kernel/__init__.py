"""
Compatibility shim: redirects any `beaker_kernel[.X]` import to `beaker_notebook[.X]`.
"""
import importlib
import sys
from importlib.abc import MetaPathFinder, Loader
from importlib.machinery import ModuleSpec

_OLD = "beaker_kernel"
_NEW = "beaker_notebook"


class _RenameLoader(Loader):
    def create_module(self, spec):
        target = _NEW + spec.name[len(_OLD):]
        module = importlib.import_module(target)
        sys.modules[spec.name] = module
        return module

    def exec_module(self, module):
        pass


class _RenameFinder(MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == _OLD or fullname.startswith(_OLD + "."):
            return ModuleSpec(fullname, _RenameLoader(), is_package=True)
        return None


# Install once.
if not any(isinstance(f, _RenameFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, _RenameFinder())

# Make `beaker_kernel` itself be `beaker_notebook`.
import beaker_notebook as _bn
sys.modules[__name__] = _bn
