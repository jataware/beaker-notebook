from dataclasses import dataclass, field, asdict
from collections import deque
from collections.abc import Mapping
import importlib.metadata
import inspect
import os
import importlib
import json
import string
from typing import Optional, ClassVar, TypedDict, TypeAlias, Any, get_origin, get_args, Union
from typing_extensions import Self, Required, NotRequired


class AppConfig:
    # Definition to come
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def asdict(self):
        return self.__dict__


class TemplateFormatter(string.Formatter):
    """Custom formatter to allow formats that match "{type}:{slug}():{attr})?"."""
    CUSTOM_TYPES = ["asset",]

    def parse(self, format_string):
        for literal_text, field_name, format_spec, conversion in super().parse(format_string):
            if field_name in self.CUSTOM_TYPES:
                yield literal_text, f"{field_name}:{format_spec}", "", None
            else:
                yield literal_text, field_name, format_spec, conversion

    def get_value(self, key, args, kwargs):
        try:
            return super().get_value(key, args, kwargs)
        except KeyError:
            return ""
formatter = TemplateFormatter()


class TemplateString(str):
    _refs: set[str]

    def __init__(self, value):
        super().__init__()
        self._refs = set(
            var_name for _, var_name, _, _ in formatter.parse(self) if var_name
        )

    def render(self, bundle: "TemplateStringBundle"):
        return formatter.format(self, **bundle.render())


TemplateBundleDict: TypeAlias = Mapping[str, TemplateString|str]


class TemplateStringBundle(Mapping[str, TemplateString]):
    app_name: TemplateString
    short_title: TemplateString
    chat_welcome_html: TemplateString

    _mapping: dict[str, TemplateString]
    _render_cache: Optional[dict[str, str]]
    _rendering: bool

    def __init__(
            self,
            assets: "list[BeakerAppAsset]" = [],
            **templates: TemplateString|str,
        ):
        self._mapping = {}
        self._render_cache = None
        self._rendering = False
        for template_slug, template_string in templates.items():
            self[template_slug] = template_string
        if assets:
            self.set_assets(assets)

    def set_assets(self, assets: "list[BeakerAppAsset]"):
        for asset in assets:
            self[f"asset:{asset.slug}:src"] = TemplateString(asset.src)
            for attr_name, attr_value in asset.attrs.items():
                self[f"asset:{asset.slug}:{attr_name}"] = TemplateString(attr_value)

    def __getitem__(self, key: str) -> TemplateString:
        return self._mapping[key]

    def __setitem__(self, key, value):
        self._render_cache = None
        if not isinstance(value, TemplateString):
            value = TemplateString(value)
        self._mapping[key] = value

    def __iter__(self):
        return self._mapping.__iter__()

    def __len__(self) -> int:
        return self._mapping.__len__()

    def update(self, **templates:Mapping[str, str|TemplateString]):
        for key, value in templates.items():
            self[key] = value

    def clone(self) -> Self:
        clone: Self = self.__class__()
        clone._mapping = {**self._mapping}
        return clone

    @property
    def rendered(self) -> bool:
        return bool(self._render_cache)

    def sort_for_render(self) -> list[tuple[str, TemplateString]]:
        # Build the graph and in-degree count
        graph: dict[str, list] = {key: [] for key in self}
        in_degree: dict[str, int] = {key: 0 for key in self}

        # Populate the graph with edges based on dependencies
        for key, item in self.items():
            for ref in item._refs:
                if ref not in self:
                    raise ValueError(f"Dependency '{ref}' for item '{key}' not found in items.")
                graph[ref].append(key)
                in_degree[key] += 1

        # Initialize the queue with items having zero in-degree (no dependencies)
        queue = deque([key for key, degree in in_degree.items() if degree == 0])
        sorted_items = []

        # Process items in topological order
        while queue:
            current = queue.popleft()
            sorted_items.append(current)

            # Decrease in-degree of dependent items
            for neighbor in graph[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # Check for cycles in the dependency graph
        if len(sorted_items) != len(self):
            raise ValueError("Cycle detected in dependencies.")

        return [(key, self[key]) for key in sorted_items]

    def render(self) -> dict[str, str]:
        try:
            self._rendering = True
            result: dict[str, str] = {}
            if self.rendered and self._render_cache:
                return self._render_cache
            else:
                for key, value in self.sort_for_render():
                    result[key] = formatter.format(value, **result)
                self._render_cache = result
                return result
        finally:
            self._rendering = False


def get_stylesheet_url(app: "BeakerApp", stylesheet: "Optional[str|TemplateString|BeakerAppAsset]" = None) -> str|None:
    if not stylesheet:
        stylesheet = app.stylesheet
    if isinstance(stylesheet, BeakerAppAsset):
        stylesheet = stylesheet.src
    if stylesheet is None:
        return None
    result = TemplateString(stylesheet).render(app._template_bundle)
    # Check if instead of a url, we end up with an asset slug. If so, return the url from the asset.
    if result in app._assets:
        asset = app._assets[result]
        if getattr(asset, "src", None):
            result = TemplateString(asset.src).render(app._template_bundle)
        else:
            raise ValueError("Stylesheet asset `%s` is missing a src attribute.", result)
    return result


AssetDict: TypeAlias = Mapping[str, str]


@dataclass
class BeakerAppAsset:
    slug: str
    src: Optional[str|TemplateString]
    attrs: dict[str, str|TemplateString]

    def __init__(
            self,
            slug: str,
            src: Optional[str|TemplateString] = None,
            attrs: Optional[dict[str,str]] = None,
            **kwargs: str
        ):
        self.slug = slug
        if src:
            self.src = src
        self.attrs = {}
        if attrs:
            self.attrs.update(attrs)
        if kwargs:
            self.attrs.update(kwargs)

    def asdict(self, app: "BeakerApp") -> AssetDict:
        return {
            "slug": self.slug,
            "src": TemplateString(self.src).render(app._template_bundle),
            **{
                key: TemplateString(value).render(app._template_bundle) for key, value in self.attrs.items()
            }
        }


ContextDict = TypedDict("ContextDict", {
    "slug": str,
    "payload": NotRequired[dict[str, Any]],
    "single_context": NotRequired[bool]
})


@dataclass
class Context:
    slug: str
    payload: dict[str, Any] = field(default_factory=lambda: {})
    single_context: bool = False
    language: Optional[str] = None
    debug: Optional[bool] = None
    verbose: Optional[bool] = None

    def asdict(self):
        context_dict = {}
        for key, value in asdict(self).items():
            # Required fields
            if key in ('slug', 'payload'):
                context_dict[key] = value
            elif value is not None:
                context_dict[key] = value
        return context_dict


PageDict = TypedDict("PageDict", {
    "slug": NotRequired[str],
    "title": NotRequired[str|TemplateString],
    "default": NotRequired[bool],
    "stylesheet": NotRequired[str|BeakerAppAsset],
    "template_bundle": NotRequired[TemplateStringBundle|dict[str, str]|dict[str, TemplateString]],
    "role": NotRequired[str],
})


@dataclass
class Page:
    slug: str
    title: Optional[str|TemplateString] = None
    default: Optional[bool] = False
    stylesheet: Optional[str|BeakerAppAsset] = None  # field(default_factory=lambda: {})
    template_bundle: Optional[TemplateStringBundle|dict[str, str]|dict[str, TemplateString]] = None

    def __post_init__(self):
        if self.title is None:
            self.title = TemplateString(f"{{app_name}} {self.slug.capitalize()}")
        if isinstance(self.stylesheet, str):
            self.stylesheet = TemplateString(self.stylesheet)

    def asdict(self, app: "BeakerApp"):
        bundle = app._template_bundle.clone()
        stylesheet = get_stylesheet_url(app, self.stylesheet)
        if self.template_bundle:
            bundle.update(**self.template_bundle)
            rendered_values = bundle.render()
            template_strings = {
                key: value
                for key, value in rendered_values.items()
                if key in self.template_bundle
            }
        else:
            template_strings = {}
        title = TemplateString(self.title).render(bundle)
        return {
            "slug": self.slug,
            "title": title,
            "default": self.default,
            "stylesheet": stylesheet,
            "template_strings": template_strings,
        }


class BeakerApp:
    """
    """

    # Configuration settings
    slug: ClassVar[str]
    name: ClassVar[Optional[str]] = None
    default_title: ClassVar[Optional[str]] = None
    asset_dir: ClassVar[Optional[os.PathLike]] = None
    assets: ClassVar[dict[str, dict[str, str|TemplateString]]] = {}
    default_context: ClassVar[Optional[Context|ContextDict]] = None
    template_bundle: ClassVar[Optional[TemplateStringBundle|TemplateBundleDict]] = None
    pages: ClassVar[list[Page|PageDict]|dict[str, Page|PageDict]] = {}
    stylesheet: ClassVar[Optional[str|BeakerAppAsset]] = None
    config: ClassVar[Optional[AppConfig]] = None

    # Internal
    _default_context: Context
    _assets: dict[str, BeakerAppAsset]
    _template_bundle: TemplateStringBundle
    _default_title: str
    _pages: dict[str, Page]

    def __init_subclass__(cls):
        if not cls.slug:
            raise ValueError("ClassVar 'slug' is required.")
        if not cls.asset_dir:
            cls_path = inspect.getfile(cls)
            cls.asset_dir = os.path.abspath(os.path.join(os.path.dirname(cls_path), "assets"))

    def __init__(self):
        self._assets = {}
        for asset_slug, asset_values in self.assets.items():
            if isinstance(asset_values, BeakerAppAsset):
                asset = asset_values
            else:
                slug = asset_values.pop("slug", asset_slug)
                asset = BeakerAppAsset(
                    slug=slug,
                    **asset_values
                )
            if hasattr(asset, "src"):
                asset.src = os.path.join("/assets", self.slug, asset.src)
            self._assets[asset_slug] = asset

        if isinstance(self.template_bundle, TemplateStringBundle):
            self._template_bundle = self.template_bundle
        elif isinstance(self.template_bundle, dict):
            self._template_bundle = TemplateStringBundle(**self.template_bundle)
        else:
            self._template_bundle = TemplateStringBundle()
        self._template_bundle["app_slug"] = TemplateString(self.slug)
        self._template_bundle["asset_path"] = TemplateString(f"/assets/{self.slug}")
        self._template_bundle.set_assets(self._assets.values())

        if self.name is None:
            try:
                package_metadata = importlib.metadata.metadata(__package__)
                name = package_metadata["Name"]
            except importlib.metadata.PackageNotFoundError:
                name = None
            if not name:
                name = self.slug
            self.name = name.capitalize().replace("_", " ")
        self._template_bundle["app_name"] = TemplateString(self.name)

        self._pages = {}
        if isinstance(self.pages, list):
            for page in self.pages:
                if isinstance(page, Page):
                    pass
                elif isinstance(page, dict):
                    page = Page(**page)
                else:
                    raise ValueError(f"Unable to initiate page of type {page.__class__.__name__}")
                self._pages[page.slug] = page
        elif isinstance(self.pages, dict):
            for slug, page in self.pages.items():
                if isinstance(page, Page):
                    pass
                elif isinstance(page, dict):
                    if slug in page:
                        page = Page(**page)
                    else:
                        page = Page(slug=slug, **page)
                else:
                    raise ValueError(f"Unable to initiate page from provided type {page.__class__.__name__}")
                self._pages[page.slug] = page
        self._default_title = TemplateString(self.default_title) if self.default_title else self.name

        if isinstance(self.default_context, Context):
            self._default_context = self.default_context
        elif isinstance(self.default_context, dict):
            self._default_context = Context(**self.default_context)


    def get_title(self, page_slug: Optional[str]=None) -> str|None:
        title = None
        if page_slug:
            if page_slug in self._pages:
                title = self._pages[page_slug].title
            else:
                if self._default_title:
                    title =  f"{self._default_title} {page_slug.capitalize()}"
                else:
                    title = r"{app_name}"
        else:
            title = self._default_title
        return TemplateString(title).render(self._template_bundle)


    @property
    def templates(self) -> dict[str, str]:
        return self._template_bundle.render()

    def as_dict(self) -> dict:
        app_dict = {}
        if self.pages:
            app_dict["pages"] = {page_slug: page.asdict(app=self) for page_slug, page in self._pages.items()}
        if self._template_bundle:
            app_dict["templateStrings"] = self.templates
        if self.default_context:
            app_dict["default_context"] = (self.default_context if isinstance(self.default_context, Context) else Context(**self.default_context)).asdict()
        if self._assets:
            app_dict["assets"] = {asset.slug: asset.asdict(self) for asset in self._assets.values()}
        if self.stylesheet:
            app_dict["stylesheet"] = get_stylesheet_url(self)
        if self.config:
            app_dict["config"] = self.config.asdict()
        return app_dict

    def to_javascript(self, page=None) -> str:
        output = [
            r"window.beaker_app = {};"
        ]

        page_title = self.get_title(page)
        if page_title:
            output.append(
                rf"""document.title = {json.dumps(page_title)};"""
            )

        if self.pages:
            output.append(
                rf"""window.beaker_app.pages = {json.dumps({page_slug: page.asdict(app=self) for page_slug, page in self._pages.items()})};"""
            )
        if self._template_bundle:
            output.append(
                rf"""window.beaker_app.templateStrings = {json.dumps(self.templates)};"""
            )
        if self.default_context:
            context = self.default_context.asdict() if isinstance(self.default_context, Context) else self.default_context
            context = self.default_context if isinstance(self.default_context, Context) else Context(**self.default_context)
            output.append(
                rf"""window.beaker_app.default_context = {json.dumps(context.asdict())};"""
            )
        if self._assets:
            output.append(
                rf"""window.beaker_app.assets = {json.dumps({asset.slug: asset.asdict(self) for asset in self._assets.values()})};"""
            )
        if self.stylesheet:
            output.append(
                rf"""window.beaker_app.stylesheet = {json.dumps(get_stylesheet_url(self))}"""
            )
        if self.config:
            output.append(
                rf"""window.beaker_app.config = {json.dumps(self.config.asdict())}"""
            )
        return "\n".join(output)
