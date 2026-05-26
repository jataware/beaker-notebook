from nbformat import NotebookNode, from_dict, writes
from traitlets.config import default
from nbconvert.exporters.notebook import NotebookExporter
from nbconvert.preprocessors import Preprocessor
from archytas.models.base import BaseArchytasModel
from beaker_kernel.lib.config import config
from uuid import uuid4

from typing import TypedDict

class StreamlineOptions(TypedDict):
    collapseCodeCells: bool
    collapseOutputs: bool
    cleanAgentErrors: bool

class StreamlinePreprocessor(Preprocessor):
    def __init__(self, **kwargs):
        self.model: BaseArchytasModel | None = None
        self.options: dict | None = None
        super().__init__(**kwargs)
    def add_title_and_abstract(self, nb: NotebookNode):
        if self.model is None:
            raise ValueError("Failed to retrieve model")
        full_text = writes(nb)
        title = self.model.invoke([f"""
            You will be provided with the contents of a Jupyter Notebook session involving an
            agent and a human working on a notebook together. Read the contents and return a title that adequately
            comprises what the goal of the notebook in a succinct and concise way, fit for a title in a header.

            Do not format the text at all, please only return plain text.
            Only return the abstract text, not anything summarizing actions that you have done.
            Do not mention stripping formatting or HTML tags.

            Below are the contents.

            ```
            {full_text}
            ```
        """]).content
        abstract = self.model.invoke([f"""
            You will be provided with the contents of a Jupyter Notebook session involving an
            agent and a human working on a notebook together. Read the contents and return an abstract.
            The abstract should be a concise, multiline description and summary
            of what happened, and how it was done.

            Important: Keep this summary concise, but accurately describe important info.

            Do not format the text at all, please only return plain text.
            Only return the abstract text, not anything summarizing actions that you have done.
            Do not mention stripping formatting or HTML tags.

            Below are the contents.

            ```
            {full_text}
            ```
        """]).content
        new_cell = from_dict({
            "id": str(uuid4()),
            "cell_type": "markdown",
            "metadata": {},
            "source": f"# {title}\n\n{abstract}"
        })
        nb.cells = [new_cell] + nb.cells
        return nb.cells
    def preprocess(self, nb: NotebookNode, resources: dict):
        for index, cell in enumerate(nb.cells):
            nb.cells[index], resources = self.preprocess_cell(cell, resources, index)
        nb.cells = [cell for cell in nb.cells if not cell.metadata.get("omitted", False)]
        nb.cells = self.add_title_and_abstract(nb)
        return nb, resources
    def preprocess_cell(self, cell: NotebookNode, resources: dict, index: int):
        if self.model is None:
            raise ValueError("Failed to retrieve model")
        if cell.cell_type == "markdown":
            if cell.metadata.get("finalResponse"):
                message = self.model.invoke([f"""
                    Here is a message from an AI agent, written in first person.
                    Strip all markdown formatting and HTML tags before adding your own for clarity.
                    Please rewrite this to be a declarative third person statement about what was done in past tense with no self talk.
                    Rather than say "The agent performed this action", say "This action was performed" in passive voice.
                    Do not say I. Preferably, do not talk about an agent at all.

                    Only return the rewritten text, not anything that you have done.
                    Do not mention stripping formatting or HTML tags.

                    Start with an h2 (##) heading in markdown in this block.

                    Below are the contents.

                    ```markdown
                    {cell.source}
                    ```"""])
                cell.source = f'{message.content}'
            elif cell.metadata.get("parentQueryCell"):
                # if we split the cell
                if "code_cell" in [event["type"] for event in cell.metadata.get("events")]:
                    message = self.model.invoke([f"""
                        Here is a user query to run code on the user's behalf.
                        Please preserve the formatting as a markdown h4 (####) header.
                        Please rewrite this to be a present participle statement about what is going to be done.
                        Examples:
                        IN: "can you plot a sine wave?"
                        OUT: "# Creating a sine wave"
                        IN: "Please fetch data from this data repository"
                        OUT: "# Fetching data from data repository"
                        IN: "Can you create a table of random data
                        ```python
                        # numpy code to create a table
                        ```"
                        OUT: "#### Creating a table of random data with Numpy"
                        as if filling out a table of contents.

                        Only return the rewritten text, not anything that you have done.
                        Do not mention stripping formatting or HTML tags.

                        Do not include anything but the header here.
                        Instead of code blocks, leave only the header.
                        Code will be added later, so do not create any annotated code blocks or summaries.

                        Below are the contents.

                        ```markdown
                        {cell.source}
                        ```"""])
                # cell hasn't been split, we need both parts
                else:
                    message = self.model.invoke([f"""
                        Here is a user query and its followup on the user's behalf.

                        Please preserve the formatting as a markdown h4 (####) header.
                        Please rewrite this to be a present participle statement about what is going to be done as a header,
                        followed by a brief summary of what happened with no self talk.
                        Examples:
                        IN: "
                            USER: Can you tell a joke?
                            Agent: Why did the functional programmer get thrown out of school?
                                   Because he refused to take classes.
                        "
                        OUT: "#### Telling a joke

                        Why did the functional programmer get thrown out of school?
                        Because he refused to take classes."

                        Only return the rewritten text, not anything that you have done.
                        Do not mention stripping formatting or HTML tags.

                        Do not include anything but the header and description here.
                        Instead of code blocks, leave only the header and description.
                        Code will be added later, so do not create any annotated code blocks or summaries.

                        Below are the contents.

                        ```markdown
                        {cell.source}
                        ```"""])
                cell.source = f'{message.content}'
            elif cell.metadata.get("beakerQueryCellChild"):
                message = self.model.invoke([f"""
                    Here is a message from an AI agent, written in first person.
                    Strip all markdown formatting and HTML tags before adding your own for clarity.
                    Please rewrite this to be a declarative third person statement about what was done in past tense with no self talk.
                    Rather than say "The agent performed this action", say "This action was performed" in passive voice.
                    Do not say I. Preferably, do not talk about an agent at all.

                    Only return the rewritten text, not anything that you have done.
                    Do not mention stripping formatting or HTML tags.

                    This is an intermediate step, so please keep it terse.
                    Avoid starting statements with interjections like "Perfect!" or "Excellent!" and remove these if present.

                    Below are the contents.

                    ```markdown
                    {cell.source}
                    ```"""])
                cell.source = f'{message.content}'
            # markdown cell without tags that imply it should be processed here: ignore and continue
            else:
                pass
        elif cell.cell_type == "code":
            if cell.metadata.get("beakerQueryCellChild") and self.options:
                if self.options.get("collapseCodeCells"):
                    cell.metadata["collapsed"] = True
                    cell.metadata["jupyter"] = cell.metadata.get("jupyter", {}) | {"source_hidden": True}
                if self.options.get("collapseOutputs"):
                    if "display_data" not in [output.output_type for output in cell.outputs]:
                        cell.metadata["jupyter"] = cell.metadata.get("jupyter", {}) | {"outputs_hidden": True}
                if self.options.get("cleanAgentErrors"):
                    if "error" in [output.output_type for output in cell.outputs]:
                        cell.metadata["omitted"] = True
        return cell, resources


class StreamlineExporter(NotebookExporter):
    """
    Exports a notebook with LLM passes to focus and sharpen the information
    to make streamlined.
    """
    export_from_notebook = "notebook"
    output_mimetype = "application/json"

    def __init__(self, **kwargs):
        self.preprocessors = [StreamlinePreprocessor]
        self.model: BaseArchytasModel | None = config.get_model()
        self.options: dict | None = None
        super().__init__(**kwargs)

    @default("file_extension")
    def _file_extension_default(self):
        return ".ipynb"

    def from_notebook_node(self, nb: NotebookNode, resources=None, **kwargs):
        if self.model is None:
            raise ValueError("Failed to get model from Beaker Kernel")
        streamline_preprocessor = next(
            preprocessor for preprocessor in self._preprocessors
            if isinstance(preprocessor, StreamlinePreprocessor)
        )
        streamline_preprocessor.model = self.model
        streamline_preprocessor.options = self.options
        output, resources = super().from_notebook_node(nb, resources, **kwargs)
        return output, resources
