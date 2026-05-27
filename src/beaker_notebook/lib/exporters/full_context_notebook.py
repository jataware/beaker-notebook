from nbformat import NotebookNode
from traitlets.config import default
from nbconvert.exporters.notebook import NotebookExporter


class FullContextNotebookExporter(NotebookExporter):
    """
    Exports a notebook without any processing.
    Returns the notebook as-is, preserving all content and metadata.
    """
    export_from_notebook = "notebook"
    output_mimetype = "application/json"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @default("file_extension")
    def _file_extension_default(self):
        return ".ipynb"

    def from_notebook_node(self, nb: NotebookNode, resources=None, **kwargs):
        # Simply call the parent method without any preprocessing
        output, resources = super().from_notebook_node(nb, resources, **kwargs)
        return output, resources
