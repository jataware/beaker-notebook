from hatchling.plugin import hookimpl

from .beaker import BeakerBuildHook
from .templates import (
    BeakerNewProjectTemplateHook, BeakerNewContextTemplateHook, BeakerNewSubkernelTemplateHook,
)


@hookimpl
def hatch_register_build_hook():
    return  [
        BeakerBuildHook,
    ]


@hookimpl
def hatch_register_template():
    return [
        BeakerNewProjectTemplateHook,
        BeakerNewContextTemplateHook,
        BeakerNewSubkernelTemplateHook,
    ]
