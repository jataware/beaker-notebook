import importlib
import sys
import types
import typing


ImportRedirectTarget: typing.TypeAlias = str | tuple[str, str]
ImportRedirectMap: typing.TypeAlias = dict[str, dict[str, ImportRedirectTarget]]


def redirect_imports(redirect_map: ImportRedirectMap):
    """
    Redirects imports from an original location to the location they have been moved to.
    """

    def _mod_getattr(mod: types.ModuleType, member: str, default: typing.Any = None):
        """
        Custom getattr function that only loads the modules on demand.
        """
        orig_member = member
        new_mod_info = mod._members.get(member, ImportError)
        if new_mod_info is ImportError:
            raise AttributeError()
        if isinstance(new_mod_info, str):
            new_mod_str = new_mod_info
        elif isinstance(new_mod_info, tuple):
            new_mod_str, member = new_mod_info
        new_mod = importlib.import_module(new_mod_str)
        result = getattr(new_mod, member, default)

        if result and result is not default:
            import warnings
            warnings.warn(
                f"Item '{orig_member}' has moved from module '{mod.__name__}' to module '{new_mod_str}'. Please update your imports.",
                DeprecationWarning,
                stacklevel=2
            )

        # Set attr directly once resolved so we don't have to go through this function in the future for the same member.
        setattr(mod, member, result)
        return result


    # Register the old locations for each of the members so they can be imported
    for mod_name, members in redirect_map.items():
        # Skip if the module already exists in sys.modules to avoid conflicts
        # with actual modules that might be executed with -m
        if mod_name not in sys.modules:
            mod = types.ModuleType(mod_name)
            mod.__dict__["_members"] = members
            setattr(mod, "__getattr__", types.MethodType(_mod_getattr, mod))
            sys.modules[mod_name] = mod
