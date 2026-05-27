from typing import TYPE_CHECKING, Any, Dict, List
import logging
logger = logging.getLogger(__name__)

from beaker_notebook.lib.context import BeakerContext
from beaker_notebook.lib.autodiscovery import autodiscover, AutodiscoveryItems

from .agent import DefaultAgent

if TYPE_CHECKING:
    from beaker_notebook.kernel import BeakerKernel
    from beaker_notebook.lib.agent import BeakerAgent
    from beaker_notebook.lib.subkernel import BeakerSubkernel


class DefaultContext(BeakerContext):
    """
    Default Beaker context

    Useful for most things out of the box, but has not been specialized.
    """

    AGENT_CLS = DefaultAgent
    WEIGHT = 10
    SLUG = "default"

    @classmethod
    def available_subkernels(cls) -> dict["str", "BeakerSubkernel"]:
        subkernels: AutodiscoveryItems[BeakerSubkernel] = autodiscover("subkernels")
        subkernel_list = sorted(subkernels.values(), key=lambda subkernel: (subkernel.WEIGHT, subkernel.SLUG))
        return {subkernel.SLUG: subkernel for subkernel in subkernel_list}

    async def generate_preview(self):
        """
        Preview what exists in the subkernel.
        """
        fetch_state_code = self.subkernel.FETCH_STATE_CODE
        result = await self.evaluate(fetch_state_code)
        state = result.get("return", None)
        return {
            "Subkernel State": {
                "state": {
                    "application/json": state or {}
                }
            },
        }
