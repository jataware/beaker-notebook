import json
import logging
import re

from archytas.tool_utils import AgentRef, LoopControllerRef, tool
from archytas.multimodal import MultiModalResponse

from beaker_kernel.lib.agent import BeakerAgent
from beaker_kernel.lib.context import BeakerContext
from beaker_kernel.lib.utils import ExecutionError


logger = logging.getLogger(__name__)


class DefaultAgent(BeakerAgent):
    """
    You are an programming assistant to aid a developer working in a Jupyter notebook by answering their questions and helping write code for them based on their
    prompt.
    """

    @tool()
    async def tell_a_joke(self, topic: str, agent: AgentRef, loop: LoopControllerRef) -> str:
        """
        Generates a joke for the user.

        Args:
            topic (str): A topic that the joke should be about. If no topic is provided, use the default value of "any".
        Returns:
            str: The text of the joke, possibly with or without formatting.
        """
        code = """
import requests
url = 'https://v2.jokeapi.dev/joke/Programming,Miscellaneous,Pun,Spooky?blacklistFlags=nsfw,religious,political,racist,sexist,explicit'
result = requests.get(url).json()
if result.get('type') == 'single':
    formatted_joke = result.get('joke')
elif result.get('type') == 'twopart':
    formatted_joke = f'''
{result.get('setup')}

{result.get('delivery')}
'''.strip()

formatted_joke
""".strip()

        try:
            context = await agent.context.evaluate(code)
            joke = context["return"]
        except ExecutionError as e:
            logger.warning(f"Error fetching joke: {e}")
            joke = """Have you ever seen an elephant hiding in a tree? Me neither. They must be VERY good at it!"""

        return joke

    # Tools defined below are examples of how to return multi-modal content from tools.
    # Commented out as I don't currently have a set of good images to pull from.

    # @tool()
    # async def random_image(self) -> MultiModalResponse:
    #     """
    #     Returns a random image.

    #     Returns:
    #         MultiModalResponse: A random image.
    #     """
    #     import random
    #     options = [
    #     ]
    #     filepath = random.choice(options)
    #     result = MultiModalResponse.from_file(filepath)
    #     return result

    # @tool()
    # async def random_images(self, count: int) -> MultiModalResponse:
    #     """
    #     Returns 3 random images. Images may be repeated.

    #     Args:
    #         count: (int) An integer between 1 and 4 inclusive indicating how many images that are sent.

    #     Returns:
    #         MultiModalResponse: 3 images as content blocks
    #     """
    #     if not isinstance(count, int) or count < 1 or count > 4:
    #         raise ValueError("Invalid argument: count. Argument must be an integer between 1 and 4 inclusive.")
    #     options = [
    #     ]
    #     result = MultiModalResponse.from_files(options[:count])
    #     return result
