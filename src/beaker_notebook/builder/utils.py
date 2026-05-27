import json


def add_beaker_subcommand(self, group_name: str, module: str, entry_point: str) -> tuple[str, str]:
    config = {
        "group_name": group_name,
        "module": module,
        "entry_point": entry_point
    }
    location = f""

    return location, json.dumps(config, indent=2)
