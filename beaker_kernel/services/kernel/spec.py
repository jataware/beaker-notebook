import traitlets
from jupyter_client import kernelspec

from beaker_kernel.app.base import BaseBeakerApp


class BeakerKernelSpecManager(kernelspec.KernelSpecManager):
    NAME_SEP = r"%%"
    parent: "traitlets.Instance[BaseBeakerApp]"

    @property
    def kernel_spec_managers(self) -> dict[str, kernelspec.KernelSpecManager]:
        """Get kernel specification managers from parent server app.

        Returns
        -------
        dict[str, kernelspec.KernelSpecManager]
            Mapping of extension names to kernel spec managers
        """
        return self.parent.kernel_spec_managers

    def get_default_kernel_name(self) -> str:
        """Get the default kernel name.

        Returns
        -------
        str
            The default kernel name (beaker_kernel)
        """
        return f"beaker_kernel"

    def _update_spec(self, name: str, spec: dict[str, dict]) -> dict[str, dict]:
        """Update kernel spec with name if not present.

        Parameters
        ----------
        name : str
            Kernel name to add to spec
        spec : dict[str, dict]
            Kernel specification dictionary

        Returns
        -------
        dict[str, dict]
            Updated kernel specification
        """
        if "name" not in spec:
            spec["name"] = name
        return spec

    def get_all_specs(self) -> dict[str, dict]:
        """Get all available kernel specifications from all managers.

        Aggregates kernel specifications from local manager and all extension
        managers, applying proper namespacing for extension specs.

        Returns
        -------
        dict[str, dict]
            Dictionary mapping kernel names to their specifications
        """
        res = {}
        for spec_slug, spec_manager in self.kernel_spec_managers.items():

            if not self.parent.kernel_spec_include_local and spec_slug is None:
                # Even we are not including local specs, we need to include beaker_kernel
                res["beaker_kernel"] = self._update_spec(spec_manager.get_all_specs()["beaker_kernel"])

            specs = spec_manager.get_all_specs().items()
            for kernel_name, spec in specs:
                if spec_slug is None:
                    key = kernel_name
                else:
                    key = f"{spec_slug}{self.NAME_SEP}{kernel_name}"
                res[key] = self._update_spec(kernel_name, spec)
        return res

    def get_kernel_spec(self, kernel_name) -> kernelspec.KernelSpec:
        """Get a specific kernel specification by name.

        Handles both local kernel specs and extension-namespaced specs.
        Extension specs use the format: extension_name%%kernel_name

        Parameters
        ----------
        kernel_name : str
            Name of the kernel spec to retrieve, optionally namespaced

        Returns
        -------
        kernelspec.KernelSpec
            The requested kernel specification

        Raises
        ------
        kernelspec.NoSuchKernel
            If the specified kernel is not found
        """
        if self.NAME_SEP in kernel_name:
            spec_slug, name = kernel_name.split(self.NAME_SEP, maxsplit=1)
        else:
            spec_slug = None
            name = kernel_name

        spec_manager = self.kernel_spec_managers.get(spec_slug, None)
        if spec_manager is None:
            raise kernelspec.NoSuchKernel(kernel_name)

        spec = spec_manager.get_kernel_spec(name)

        if spec is None:
            raise kernelspec.NoSuchKernel(kernel_name)

        return spec
