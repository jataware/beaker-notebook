import importlib
import json
import logging
import os
import sys
import typing
import warnings
from collections.abc import Mapping, ItemsView
from importlib.metadata import entry_points, EntryPoints, EntryPoint
from traceback import format_exc


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

    # Temporary transitional storage for use while migrating from json files to entrypoints
    raw_jsons: dict[str, type|dict[str, str]]

    class AutodiscoveryItemsView(ItemsView):
        """
        A view class that overrides the default ItemsView to handle exceptions during iteration.
        Prevents the entire application from failing if an extension cannot be loaded.
        """
        def __init__(self, mapping: "AutodiscoveryItems"):
            super().__init__(mapping)

        def __iter__(self):
            for key in self._mapping:
                try:
                    yield (key, self._mapping[key])
                except Exception as err:
                    output = [
                        f"Unable to load autodiscovery item '{key}'. Error: {err}",
                         "  Exception traceback when loading item:",
                        f"  ================ Traceback Start ================",
                    ]
                    indented_tb = [f"    {line}" for line in format_exc().splitlines()]
                    output.extend(indented_tb)
                    output.append(
                        f"  ================ Traceback Done =================",
                    )
                    logger.warning("\n".join(output))
                    continue

    def __init__(self, entrypoints_instance: EntryPoints):
        self.raw = entrypoints_instance
        self.mapping = {
            item.name: item for item in self.raw
        }
        self.raw_jsons = {}

    def __getitem__(self, key):
        # Loading from etrypoints is the new preferred method.
        # Load class from entrypoint
        item: EntryPoint = self.mapping.get(key, None)
        if item:
            item = item.load()
            return item

        # Fallback to loading from old json file
        item = self.mapping.get(key, self.raw_jsons.get(key))
        if isinstance(item, (str, bytes, os.PathLike)) and os.path(path := os.fspath(item)) and path.endswith('.json'):
            with open(path) as jsonfile:
                item = json.load(jsonfile)
                item["mapping_file"] = path
        match item:
            case type():
                return item
            case {"slug": slug, "package": package, "class_name": class_name, **kw}:
                mapping_file = kw.get("mapping_file", None)
                module = importlib.import_module(package)
                assert slug == key, f"Autoimported item's slug ('{slug}') does not match key ('{key}')"
                discovered_class = getattr(module, class_name)
                if mapping_file:
                    setattr(discovered_class, '_autodiscovery', {
                        "mapping_file": mapping_file,
                        **item
                    })
                self.mapping[key] = discovered_class
                return discovered_class
            case _:
                raise ValueError(f"Unable to handle autodiscovery item '{item}' (type '{item.__class__}')")

    def add_json_mapping(self, key: str, value: type|dict[str, str]):
        self.raw_jsons[key] = value

    def __iter__(self):
        yield from self.mapping.keys()
        yield from self.raw_jsons.__iter__()

    def items(self):
        return self.AutodiscoveryItemsView(self)

    def __len__(self):
        return len(self.raw) + len(self.raw_jsons)


def autodiscover(mapping_type: ResourceType) -> typing.Dict[str, type]:
    """
    Auto discovers installed classes of specified types.
    """
    group = f"beaker.{mapping_type}"
    eps = entry_points(group=group)
    items: AutodiscoveryItems = AutodiscoveryItems(eps)

    # Add legacy json mappings
    for mapping_file, data in find_mappings(mapping_type):
        slug = data["slug"]
        items.add_json_mapping(slug, {"mapping_file": mapping_file, **data})
        warnings.warn(
            (
                f"Beaker is loading {mapping_type} from legacy JSON mapping file {mapping_file}.\n"
                f"    This package should be rebuilt using entrypoints for better performance and reliability."
            ),
            DeprecationWarning
        )
    return items
