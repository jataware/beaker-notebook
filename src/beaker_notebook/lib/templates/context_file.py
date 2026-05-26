from pathlib import Path
from hatchling.plugin import hookimpl
from hatch.template.plugin.interface import TemplateInterface
from hatch.template import File
from hatch.template.files_default import PyProject

from . import TemplateFile, PathTemplate
from .paths import package_name, context_subdir


class ContextFile(TemplateFile):
    PATH_PARTS = [
        'context.py',
    ]

    TEMPLATE = """\
from typing import Dict, Any, Optional, TYPE_CHECKING

from beaker_kernel.lib import BeakerContext
from beaker_kernel.lib.utils import action

from .agent import {agent_class}

if TYPE_CHECKING:
    from beaker_kernel.kernel import BeakerKernel


class {context_class}(BeakerContext):
    \"\"\"
    This is the context class.
    \"\"\"

    AGENT_CLS = {agent_class}
    SLUG = "{context_name}"

    compatible_subkernels = ["python3"]

    def __init__(self, beaker_kernel: "BeakerKernel", config: Optional[Dict[str, Any]] = None):
        super().__init__(beaker_kernel, config=config)

    async def setup(self, context_info=None, parent_header=None):
        # Custom setup can be done here
        pass

    @action(default_payload='{{\\n  "question": "Will I find love?"\\n}}')
    async def ask_eight_ball(self, message):
        \"\"\"
        An example of an action. This just calls the existing tool defined on the agent.
        \"\"\"
        content = message.content
        question = content.get("question")
        self.beaker_kernel.log("ask_eight_ball", f"Asking question: {{question}}")
        result = await self.agent.magic_eight_ball(content.get("question"))
        self.beaker_kernel.log("ask_eight_ball", f"Got answer: {{result}}")
        return str(result)

"""
