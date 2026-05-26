from . import TemplateFile


class ProcedureFile(TemplateFile):
    PATH_PARTS = [
        'procedures',
        'python3',
        'example.py',
    ]

    TEMPLATE = """\
# This is an example procedure template.
# Procedures are code snippets that can be rendered with Jinja2 and executed
# in the subkernel via self.get_code("example") and self.evaluate().
#
# You can use Jinja2 template variables like {{ '{{' }} variable_name {{ '}}' }}
# and they will be substituted when you call self.get_code("example", {{"variable_name": value}}).

result = "Hello from the example procedure!"
result
"""
