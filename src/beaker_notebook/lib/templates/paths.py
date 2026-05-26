"""
Stores commonly reused path templates
"""

from . import PathTemplate

package_name = PathTemplate("{package_name}")

context_subdir = PathTemplate(
    "{context_subdir}",
    condition=lambda template_values: template_values.get("context_subdir", None) != None,
)
