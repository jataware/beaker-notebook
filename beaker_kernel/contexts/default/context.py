from typing import TYPE_CHECKING, Any, Dict, List
import logging
logger = logging.getLogger(__name__)

from beaker_kernel.lib.context import BeakerContext
from beaker_kernel.lib.autodiscovery import autodiscover

from .agent import DefaultAgent

if TYPE_CHECKING:
    from beaker_kernel.kernel import BeakerKernel
    from beaker_kernel.lib.agent import BeakerAgent
    from beaker_kernel.lib.subkernel import BeakerSubkernel

class DefaultContext(BeakerContext):
    """
    Default Beaker context

    Useful for most things out of the box, but has not been specialized.
    """

    agent_cls: "BeakerAgent" = DefaultAgent

    WEIGHT: int = 10
    SLUG: str = "default"

    def __init__(self, beaker_kernel: "BeakerKernel", config: Dict[str, Any]):
        super().__init__(beaker_kernel, self.agent_cls, config)

    @classmethod
    def available_subkernels(cls) -> List["BeakerSubkernel"]:
        subkernels: Dict[str, BeakerSubkernel] = autodiscover("subkernels")
        subkernel_list = sorted(subkernels.values(), key=lambda subkernel: (subkernel.WEIGHT, subkernel.SLUG))
        subkernel_slugs = [subkernel.SLUG for subkernel in subkernel_list]
        return subkernel_slugs

    async def auto_context(self):
        return f"""
        If you need to generate code, you should write it in the '{self.subkernel.DISPLAY_NAME}' language for execution
        in a Jupyter notebook using the '{self.subkernel.KERNEL_NAME}' kernel.
        """.strip()

    async def generate_preview(self):
        """
        Preview what exists in the subkernel.
        """
        fetch_state_code = self.subkernel.FETCH_STATE_CODE
        result = await self.evaluate(fetch_state_code)
        state = result.get("return", None)
        return {
            "x-application/beaker-subkernel-state": {
                "state": {
                    "application/json": state or {}
                }
            },
        }
