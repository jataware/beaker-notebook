import binascii
import importlib.resources
import dotenv
import importlib
import inspect
import logging
import os
import tempfile
import toml
from dataclasses import dataclass, field, MISSING, asdict, is_dataclass
from enum import Enum
from pathlib import Path
from copy import deepcopy
from typing import Callable, Any, TypeVar, Generic, Literal, get_args, get_origin, Mapping

from beaker_notebook.lib.utils import DefaultModel

logger = logging.getLogger(__name__)


def get_providers() -> dict[str, str]:
    import archytas.models
    from archytas.models.base import BaseArchytasModel
    base_class = BaseArchytasModel
    result = {}
    for resource in importlib.resources.files(archytas.models).iterdir():
        if resource.is_file() and resource.name.endswith('.py'):
            name = resource.name.split('.', 1)[0]
            mod_name = f'archytas.models.{name}'
            mod = importlib.import_module(mod_name, 'archytas.models')
            items = inspect.getmembers(
                mod,
                lambda item:
                    isinstance(item, type) and \
                    issubclass(item, base_class) and \
                    item is not base_class
            )
            result.update({item[0]: f"{item[1].__module__}.{item[1].__name__}" for item in items})
    return result


CONFIG_FILE_SEARCH_LOCATIONS = [  # (path, filename, check_parent_paths, default)
    (Path.cwd(), ".beaker.conf", True, False),
    (Path("~/.config").expanduser(), 'beaker.conf', False, True),
    (Path("~").expanduser(), '.beaker.conf', False, False),
]


def locate_config(start_path: str|Path|None = None) -> Path | None:
    """
    Returns the location of the used Beaker config file or default location is no config file is found
    """
    # Avoid circular imports
    from .utils import find_file_along_path

    default_location = None
    if start_path is not None:
        locations = [(Path(start_path), '.beaker.conf', True, True)] + CONFIG_FILE_SEARCH_LOCATIONS
    else:
        locations = CONFIG_FILE_SEARCH_LOCATIONS
    for path, filename, recurse, is_default in locations:
        if recurse:
            location = find_file_along_path(filename, path)
        else:
            location = Path(path) / filename
        if isinstance(location, Path):
            if location.exists():
                return location
            if is_default and default_location is None:
                default_location = location
    return default_location


def locate_envfile() -> str:
    """
    Returns the location of the used envfile or default location is no envfile found
    """
    envfile = dotenv.find_dotenv()
    if envfile:
        envfile = os.path.abspath(envfile)
    else:
        envfile = os.path.abspath(os.path.join(os.path.curdir, ".env"))
    return envfile


def new_token():
    return binascii.hexlify(os.urandom(24)).decode("ascii")


def normalize_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    elif isinstance(value, str):
        # Hard-coded "True" values. Anything else is False.
        return value.lower() in ('true', 'y', 't', '1')
    else:
        return False


def configfield(
    description: str,
    env_var: str = MISSING,
    *,
    default = MISSING,
    default_factory = MISSING,
    sensitive: bool = False,
    aliases: list[str] = None,
    save_default_value: bool = False,
    normalize_function: Callable[[Any], Any] = MISSING,
    placeholder_text: str = MISSING,
    label: str = MISSING,
    options: Callable[[], list[Any]] = MISSING,
    **extra: dict[str, Any],
):
    def dynamic_factory():
        # Get value if defined
        if env_var and env_var != MISSING:
            env_value = os.getenv(env_var, default=MISSING)
        else:
            env_value = MISSING

        # If not defined and aliases are defined, check the aliases
        if env_value is MISSING and isinstance(aliases, list):
            for alias in aliases:
                alias_value = os.getenv(alias, default=MISSING)
                if alias_value is not MISSING:
                    env_value = alias_value
                    break

        # Fill in default definitions based on above findings and arguments
        if env_value is not MISSING:
            value = env_value
        elif default is not MISSING:
            value = default
        elif default_factory is not MISSING:
            value = default_factory()

        if normalize_function is not MISSING:
            value = normalize_function(value)
        return value

    metadata = {
        "description": description,
        "sensitive": sensitive,
        "aliases": aliases,
        "save_default_value": save_default_value,
        "extra": extra,
    }
    if env_var and env_var is not MISSING:
        metadata["env_var"] = env_var
    if placeholder_text is not MISSING:
        metadata["placeholder_text"] = placeholder_text
    if label is not MISSING:
        metadata["label"] = label
    if options is not MISSING:
        metadata["options"] = options
    return field(
        metadata=metadata,
        default_factory=dynamic_factory,
    )


T = TypeVar("T")
C = TypeVar("C")

class Table(dict[str, T]):
    pass

class Choice(Generic[C]):
    @classmethod
    def default_value(cls):
        return None


@dataclass
class LLM_Service_Provider:
    import_path: str = configfield(
        description="Dot-separated import path to the LLM Service Provider class.",
        default="archytas.models.openai.OpenAIModel",
        options=get_providers,
        save_default_value=True,
    )
    default_model_name: str = configfield(
        description="Name of the default model to use with this provider.",
        default="gpt-4o",
        save_default_value=True,
    )
    api_key: str = configfield(
        description="API key or token for authenticating to the provider, if required.",
        default="",
        sensitive=True,
        save_default_value=True,
    )
    summarization_threshold_pct: int = configfield(
        description="Percentage of the total model's available context window to allow to be used prior to summarizing.",
        default=20,
        save_default_value=True,
        min=0,
        max=100,
    )

    @classmethod
    def default_value(cls):
        return asdict(cls())


@dataclass
class ConfigClass:
    jupyter_server: str = configfield(
        "URL of Jupyter or Beaker Server which manages subkernels.",
        "JUPYTER_SERVER",
        default="http://localhost:8888",
        save_default_value=False,
    )
    jupyter_token: str = configfield(
        "Token to use when communicating with the Jupyter/Beaker server.",
        "JUPYTER_TOKEN",
        default=None,
        save_default_value=False,
    )
    provider: Choice[Literal["providers"]] = configfield(
        description="LLM model provider to use. Maps to archytas model classes.",
        env_var="LLM_SERVICE_PROVIDER",
        default_factory=lambda: "openai",
        save_default_value=True,
    )
    enable_checkpoints: bool = configfield(
        # NOTE: Checkpointing is temporarily disabled in code (see
        # beaker_notebook.lib.subkernel.is_checkpointing_enabled) due to a performance issue where
        # serializing kernel state can take several minutes in some cases. This flag is currently
        # a no-op and is retained so the configuration surface does not change when checkpointing
        # is revisited in a future update.
        "Flag as to whether checkpoints are enabled or not. Currently disabled regardless of this "
        "setting pending a fix for slow kernel-state serialization.",
        "ENABLE_CHECKPOINTS",
        default=True,
        sensitive=False,
        normalize_function=normalize_bool,
        label="Enable Checkpointing?"
    )
    beaker_run_path: os.PathLike = configfield(
        description="Path to use for beaker run items such as kernel json files and checkpoint data",
        env_var="BEAKER_RUN_PATH",
        default_factory=lambda: os.path.expanduser("~/.local/share/beaker/runtime"),
        save_default_value=False,
    )
    send_notebook_state: bool = configfield(
        description="Flag as to whether to include the state of the notebook on agent query execution.",
        env_var="SEND_NOTEBOOK_STATE",
        default=False,
        sensitive=False,
        normalize_function=normalize_bool,
        label="Send notebook state on query?"
    )
    send_kernel_state: bool = configfield(
        description="Flag as to whether to include the state of the subkernel on agent query execution.",
        env_var="SEND_KERNEL_STATE",
        default=True,
        sensitive=False,
        normalize_function=normalize_bool,
        label="Send kernel state on query?"
    )
    kernel_state_sample_budget: int = configfield(
        description="Maximum total characters of variable-sample content included in kernel_state payloads. 0 disables samples.",
        env_var="KERNEL_STATE_SAMPLE_BUDGET",
        default=0,
        sensitive=False,
        label="Kernel state sample budget (0 = use subkernel default)"
    )
    describe_variables_sample_budget: int = configfield(
        description="Maximum total characters of variable-sample content included in describe_variables payloads. 0 = use subkernel default.",
        env_var="DESCRIBE_VARIABLES_SAMPLE_BUDGET",
        default=0,
        sensitive=False,
        label="describe_variables sample budget (0 = use subkernel default)"
    )

    @property
    def checkpoint_storage_path(self):
        return os.path.join(self.beaker_run_path, "checkpoints")

    tools_enabled: Table[bool] = configfield(
        description="This table allows you to enable/disable tools. The key is the name of the tool, and the value is a \
boolean value which will enable/disable the tool based on the value.",
        default_factory=lambda: {
            "ask_user": True,
            "run_code": True,
        },
        label="Enabled?",
        save_default_value=True,
    )

    providers: Table[LLM_Service_Provider] = configfield(
        description="Allows switching between LLM Model providers/APIs.",
        save_default_value=True,
        default_factory=lambda: {
            "openai": {
                "import_path": "archytas.models.openai.OpenAIModel",
                "default_model_name": "gpt-4o-mini",
                "api_key": ""
            },
            "anthropic": {
                "import_path": "archytas.models.anthropic.AnthropicModel",
                "default_model_name": "claude-3-5-sonnet-20241022",
                "api_key": ""
            },
            "bedrock": {
                "import_path": "archytas.models.bedrock.BedrockModel",
                "default_model_name": "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
                "api_key": ""
            },
            "gemini": {
                "import_path": "archytas.models.gemini.GeminiModel",
                "default_model_name": "gemini-1.5-pro",
                "api_key": ""
            },
            "groq": {
                "import_path": "archytas.models.groq.GroqModel",
                "default_model_name": "llama3-8b-8192",
                "api_key": ""
            },
            "ollama": {
                "import_path": "archytas.models.ollama.OllamaModel",
                "default_model_name": "mistral-nemo",
                "api_key": ""
            },
        },
    )

    model_provider_import_path: str = configfield(
        "Dotted import path to archytas provider model. (Overrides value for selected provider)",
        "LLM_PROVIDER_IMPORT_PATH",
        default="",
        sensitive=False,
        save_default_value=False,
        placeholder_text="Set this value to override default.",
    )

    model_name: str = configfield(
        "Name of LLM model to use. (Overrides value for selected provider)",
        "LLM_SERVICE_MODEL",
        default="",
        sensitive=False,
        save_default_value=False,
        placeholder_text="Set this value to override default.",
    )

    llm_service_token: str | None = configfield(
        "API key used for authenticating to the LLM service, if required. (Overrides value for selected provider)",
        "LLM_SERVICE_TOKEN",
        default="",
        sensitive=True,
        save_default_value=False,
        placeholder_text="Set this value to override default.",
    )


    @classmethod
    def from_config_file(cls, config_file_path: Path|str|None = None, load_dotenv=True, **kwargs):
        config_file = locate_config(start_path=config_file_path)
        if config_file and config_file.exists():
            try:
                text = config_file.read_text()
                config_data = toml.loads(text)
            except toml.TomlDecodeError as err:
                if not text:
                    text = '<Error reading file>'
                logger.error(
                    f"""\
Error while parsing config file '{config_file.absolute()}':
{err}

File first line:
```
{text.splitlines()[0]}
```

Proceding with default values.
""",
                    exc_info=True
                )
                config_data = {}
        else:
            config_data = {}

        if load_dotenv and config_data.get("LOAD_DOTENV", True):
            # Ensure that the latest envfile is loaded
            env_file = locate_envfile()
            dotenv.load_dotenv(dotenv_path=env_file)

        # Override defaults with passed in keyword values
        config_data.update(kwargs)

        # Create instance, passing in only options that are defined as fields
        instance = cls(**{
            option: value
            for option, value in config_data.items()
            if option in cls.__dataclass_fields__ and not option.startswith('_')
        })

        return instance

    def update(self, updates: dict, config_file_path: Path|str|None = None):
        if config_file_path is None:
            config_file = locate_config(start_path=config_file_path)
        else:
            config_file = Path(config_file_path)
        if config_file.exists():
            config_data = toml.loads(config_file.read_text())
        else:
            config_data = {}
        print(f"Writing to {config_file}")
        for var_name, value in updates.items():
            self.__dict__[var_name] = value
            config_data[var_name] = value
        config_file.write_text(toml.dumps(config_data))


class Config(ConfigClass):
    """Lazy loading wrapper around ConfigClass"""
    config_obj: ConfigClass | None
    defaults: dict[str, Any]
    config_type: "Config.ConfigTypes"

    class ConfigTypes(str, Enum):
        FILE = "file"
        SESSION = "session"
        SERVER = "server"
        SINGLE_CONTEXT = "single"
        OTHER = "other"

    def __init__(self, **kwargs) -> None:
        self.config_obj = None
        config_type_str: str = kwargs.pop("config_type", os.environ.get("CONFIG_TYPE", "file"))
        self.config_type = getattr(self.ConfigTypes, config_type_str.upper(), self.ConfigTypes.FILE)
        self.defaults = kwargs
        if self.config_type == self.ConfigTypes.SERVER:
            if not os.path.isdir(self.checkpoint_storage_path):
                os.makedirs(self.checkpoint_storage_path, exist_ok=True, mode=0o777)
            if os.stat(self.checkpoint_storage_path).st_mode & 0o777 != 0o777:
                os.chmod(self.checkpoint_storage_path, 0o777)

    def __getattr__(self, name: str):
        if name in (['__dataclass_fields__', '__dataclass_params__'] + list(ConfigClass.__dataclass_fields__.keys())):
            if not self.config_obj:
                if self.config_type == self.ConfigTypes.FILE:
                    self.config_obj = ConfigClass.from_config_file(**self.defaults)
                else:
                    self.config_obj = ConfigClass(**self.defaults)
            return getattr(self.config_obj, name)
        raise AttributeError

    def get_model(self, provider_id=None, model_config=None, **config_overrides):
        from archytas.exceptions import AuthenticationError
        config_obj: dict | None = None

        if provider_id:
            config_obj = self.providers.get(provider_id, None)
            if config_obj:
                # Copying config so it doesn't get changed globally if modified in the model instance
                config_obj = deepcopy(config_obj)
            if isinstance(config_obj, dict) and isinstance(model_config, dict):
                config_obj.update(model_config)
        elif isinstance(model_config, dict):
            config_obj = model_config

        # Fetch config if model_config is None or empty.
        if not config_obj:
            # Get model from config,opying config so it doesn't get changed globally if modified in the model instance
            config_obj: dict = deepcopy(self.providers.get(self.provider, {}))

            # Update config with passed in overrides
            config_obj.update(config_overrides)

            # Override defaults if set
            if self.model_provider_import_path:
                config_obj["import_path"] = self.model_provider_import_path
            if self.model_name:
                config_obj["model_name"] = self.model_name
            if self.llm_service_token:
                config_obj["api_key"] = self.llm_service_token

        # import_path key is required. If we don't have one, we don't have a valid provider.
        if not "import_path" in config_obj:
            return None

        if "model_name" not in config_obj and "default_model_name" in config_obj:
            config_obj["model_name"] = config_obj["default_model_name"]

        module_name, cls_name = config_obj.pop("import_path").rsplit('.', 1)
        module = importlib.import_module(module_name)

        cls = getattr(module, cls_name, None)
        if cls and isinstance(cls, type):
            try:
                return cls(config_obj)
            except AuthenticationError:
                return DefaultModel({})
        else:
            raise ImportError(f"Unable to load model identified by '{module_name}.{cls_name}'. Please make sure it is properly installed.")

config = Config()


def reset_config():
    config.config_obj = None


def recursiveOptionalUpdate(obj: Any, update_obj: Any, obj_type=None, remove_missing=True):
    try:
        if obj_type is None:
            obj_type = obj.__class__
        if is_dataclass(obj):
            result = {}
            for field_name, field in obj.__dataclass_fields__.items():
                field_value = getattr(obj, field_name)
                new_value = recursiveOptionalUpdate(field_value, update_obj.get(field_name, None), obj_type=field.type, remove_missing=remove_missing)
                result[field_name] = new_value
            return result
        elif is_dataclass(obj_type):
            result = {}
            if not isinstance(update_obj, Mapping):
                update_obj = {}
            for field_name, field in obj_type.__dataclass_fields__.items():
                field_value = obj.get(field_name, field.default_factory())
                new_value = recursiveOptionalUpdate(field_value, update_obj.get(field_name, None), obj_type=field.type, remove_missing=remove_missing)
                result[field_name] = new_value
            return result
        elif isinstance(obj, Table) or (get_origin(obj_type) is not None and issubclass(get_origin(obj_type), Table)):
            # Recursively update all values in the dict-like table.
            # Use keys from update_obj when building to ensure adding-removing items is respected.
            if isinstance(update_obj, Mapping):
                if remove_missing:
                    keys = list(update_obj.keys())
                else:
                    # Join sets of keys while retaining natural order, with any newly added keys at the bottom
                    keys = list(obj.keys())
                    keys += [key for key in update_obj.keys() if key not in keys]

                result = {
                    key:  recursiveOptionalUpdate(obj.get(key, {}), update_obj.get(key, None), get_args(obj_type)[0], remove_missing=remove_missing)
                    for key in keys
                }
            else:
                result = obj
            return result
        else:
            return update_obj if update_obj is not None else obj
    except Exception as err:
        raise
