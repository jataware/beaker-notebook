import json
import logging
import os
import sys
import typing
from collections.abc import Mapping
from importlib.metadata import entry_points, EntryPoints, EntryPoint


logger = logging.getLogger(__name__)

# Sorted from more general to more specific. Items discovered lower/more specific locations will override
# more general items with the same slug.
if sys.platform == "win32":
    RAW_LIB_LOCATIONS = [
        r'%PROGRAMDATA\beaker',
        r'%APPDATA%\beaker',
        r'%LOCALAPPDATA%\beaker',
        os.path.join(sys.prefix, "share", "beaker"),
    ]
elif sys.platform == "darwin":
    RAW_LIB_LOCATIONS = [
        "/usr/share/beaker",
        "/usr/local/share/beaker",
        os.path.join(sys.prefix, "share", "beaker"),
        os.path.expanduser("~/.local/share/beaker"),
        os.path.expanduser("~/Library/Beaker"),
    ]
else:
    RAW_LIB_LOCATIONS = [
        "/usr/share/beaker",
        "/usr/local/share/beaker",
        os.path.join(sys.prefix, "share", "beaker"),
        os.path.expanduser("~/.local/share/beaker"),
    ]
    if "XDG_DATA_HOME" in os.environ:
        RAW_LIB_LOCATIONS.append(os.path.join(os.environ["XDG_DATA_HOME"], "beaker"))

RAW_LIB_LOCATIONS.extend(
    [
        os.path.expanduser("~/.config/beaker"),
        os.path.expanduser("~/.beaker"),
        os.path.abspath("./beaker"),
        os.path.abspath("./.beaker"),
    ]
)
# Ensure locations are unique without affecting order
LIB_LOCATIONS = []
for location in RAW_LIB_LOCATIONS:
    if location not in LIB_LOCATIONS and os.path.exists(location):
        LIB_LOCATIONS.append(location)

ResourceType = typing.Literal["contexts", "subkernels", "apps", "commands", "integrations", "data"]

def find_resource_dirs(resource_type: str, extra_locations: typing.Optional[list[os.PathLike]]=None) -> typing.Generator[os.PathLike, None, None]:
    """
    Returns existing resource directories in increasing order of specificity.
    I.e. the first result is the most general and the last result is the most specific to the user.
    """
    # Create a copy of LIB_LOCATIONS to prevent altering the original
    locations = LIB_LOCATIONS[:]
    if extra_locations:
        locations.extend(extra_locations)
    for location in locations:
        resource_dir = os.path.join(location, resource_type)
        if os.path.exists(resource_dir):
            yield resource_dir


def find_mappings(resource_type: ResourceType) -> typing.Generator[typing.Dict[str, any], None, None]:
    """
    Finds, reads, and parses all mappings of the provided type.
    """
    for resource_dir in find_resource_dirs(resource_type):
        for mapping in os.listdir(resource_dir):
            fullpath = os.path.join(resource_dir, mapping)
            if not fullpath.endswith(".json"):
                continue
            try:
                with open(fullpath) as mapping_file:
                    data = json.load(mapping_file)
                    yield fullpath, data
            except (json.JSONDecodeError, KeyError) as err:
                logger.error(f"Unable to parse the {resource_type} file '{fullpath}", exc_info=err)
                continue


class AutodiscoveryItems(Mapping[str, type]):
    raw: EntryPoints
    mapping: dict[str, EntryPoint]

    def __init__(self, entrypoints_instance: EntryPoints):
        self.raw = entrypoints_instance
        self.mapping = {
            item.name: item for item in self.raw
        }

    def __getitem__(self, key):
        try:
            item: EntryPoint = self.mapping.get(key, None)
            if item:
                item = item.load()
        except ImportError:
            raise

        return item
    def __iter__(self):
        yield from self.mapping.keys()

    def __len__(self):
        return len(self.raw)


def autodiscover(mapping_type: ResourceType) -> typing.Dict[str, type]:
    """
    Auto discovers installed classes of specified types.
    """
    group = f"beaker.{mapping_type}"
    eps = entry_points(group=group)
    return AutodiscoveryItems(eps)
