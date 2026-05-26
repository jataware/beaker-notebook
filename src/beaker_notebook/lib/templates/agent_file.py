from pathlib import Path
from hatchling.plugin import hookimpl
from hatch.template.plugin.interface import TemplateInterface
from hatch.template import File
from hatch.template.files_default import PyProject

from . import TemplateFile, PathTemplate
from .paths import package_name, context_subdir


class AgentFile(TemplateFile):

    PATH_PARTS = [
        'agent.py'
    ]

    TEMPLATE = """\
from typing import TYPE_CHECKING

from archytas.tool_utils import tool
from beaker_notebook.lib import BeakerAgent

if TYPE_CHECKING:
    from beaker_notebook.kernel import BeakerKernel


class {agent_class}(BeakerAgent):
    \"\"\"
    You are a helpful agent that will answer questions and help with what is asked of you.
    \"\"\"

    # The class docstring is provided to the LLM to set the expectations for the agent and how it should behave.
    # A sample tool to get you started.
    # Notice that the doc-string provides instructions to the agent about how and when to use the tools along with the
    # expected inputs and outputs, including the datatype what they represent so the agent knows how to prepare proper
    # input and how to use the output of the tool.
    @tool()
    async def magic_eight_ball(self, question: str) -> str:
        \"\"\"
        This is an example tool that is provided to help users understand how tools work in Beaker. It should only be
        used when a user explicitly asks for it.

        This simulates a Magic 8 ball toy where a person asks questions and gets answers indicating yes/no/maybe.

        If the tool returns the value "rephrase", the agent should use the ask_user tool to rephrase the question and
        then rerun this tool with the new question.

        Args:
            question (str): The question the user would like to have answered. The question must be answerable as
                            yes/no/maybe. If the question is not a yes/no/maybe question then inform the user, using the
                            ask_user tool for them reword the question so that it is a proper question before proceding.
        Returns:
            str: A string that is either the response the magic eight ball returned or the token "rephrase".
        \"\"\"
        import random
        choices = [
            "rephrase",
            "Signs point to yes!",
            "Doesn't look good...",
            "My sources say no.",
            "I asked Siri and she said it's a secret.",
            f"How on earth do can you think that '{{question.strip()}}' is an appropriate question to ask me!?!?",
            "Yes, duh!",
            "No way, Jose!",
        ]
        if question.startswith("sudo"):
            return "Your wish is granted!"
        return random.choice(choices)

"""
