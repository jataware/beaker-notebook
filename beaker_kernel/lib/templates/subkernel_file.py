from pathlib import Path
from hatchling.plugin import hookimpl
from hatch.template.plugin.interface import TemplateInterface
from hatch.template import File
from hatch.template.files_default import PyProject

from . import TemplateFile, PathTemplate
from .paths import package_name, context_subdir


class SubkernelFile(TemplateFile):
    PATH_PARTS = [
        'subkernel.py',
    ]

    TEMPLATE = """\
import json
import logging
from typing import Any

from beaker_kernel.lib import BeakerSubkernel

logger = logging.getLogger(__name__)


class {subkernel_class_name}(BeakerSubkernel):
    \"\"\"
    Beaker subkernel on top of the `{kernel_name}` ({kernel_package}) kernel.
    \"\"\"
    DISPLAY_NAME = "{subkernel_display_name}"
    SLUG = "{subkernel_slug}"
    KERNEL_NAME = "{kernel_name}"

    WEIGHT = 50

    @classmethod
    def parse_subkernel_return(cls, execution_result) -> Any:
        \"\"\"
        Used to evaluate the results from the native kernel language into the Beaker Kernel Python environment.

        This value is then accessible to the kernel via the response to `beaker_kernel.evaluate()` command as a
        native Python object.
        \"\"\"

        # TODO: Update code to work with outputs
        return_str = execution_result.get("return", None)
        return return_str


"""
