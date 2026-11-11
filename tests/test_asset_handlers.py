from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from tornado.testing import AsyncHTTPTestCase
from tornado.web import Application, RequestHandler

from beaker_notebook.app.base import BaseBeakerApp


class NotFoundHandler(RequestHandler):
    def get(self, path):
        self.set_status(404)


class AssetHandlerTest(AsyncHTTPTestCase):
    base_url = "/nested/beaker/"

    def get_app(self):
        self.assets = TemporaryDirectory()
        self.addCleanup(self.assets.cleanup)
        root = Path(self.assets.name)
        context_dir = root / "context"
        app_dir = root / "app"
        context_dir.mkdir()
        app_dir.mkdir()
        (context_dir / "renderer.js").write_text("context asset")
        (app_dir / "logo.svg").write_text("app asset")

        context = SimpleNamespace(slug="example", asset_dir=context_dir)
        beaker_app = SimpleNamespace(slug="example-app", asset_dir=app_dir, pages={})
        web_app = Application([(r"(.*)", NotFoundHandler)])
        self.beaker = SimpleNamespace(
            base_url=self.base_url,
            handlers=[],
            web_app=web_app,
            context_manager=SimpleNamespace(list_contexts=lambda: [context]),
            config={"app": beaker_app},
            ui_path=root,
        )
        with patch("beaker_notebook.app.handlers.register_api_handlers"):
            BaseBeakerApp.initialize_handlers(self.beaker)
        return web_app

    def test_context_and_app_assets(self):
        for path, content in (
            ("assets/context/example/renderer.js", b"context asset"),
            ("assets/example-app/logo.svg", b"app asset"),
        ):
            response = self.fetch(f"{self.base_url}{path}")
            assert response.code == 200
            assert response.body == content

    def test_registered_patterns_include_prefix(self):
        patterns = [handler[0] for handler in self.beaker.handlers]
        assert f"{self.base_url}assets/context/example/(.*)" in patterns
        assert f"{self.base_url}assets/example-app/(.*)" in patterns

    def test_missing_asset_returns_404(self):
        response = self.fetch(f"{self.base_url}assets/context/example/missing.js")
        assert response.code == 404

    def test_unprefixed_asset_is_not_registered(self):
        if self.base_url != "/":
            response = self.fetch("/assets/context/example/renderer.js")
            assert response.code == 404


class RootAssetHandlerTest(AssetHandlerTest):
    base_url = "/"
