import json
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import pytest

from beaker_notebook.app.handlers import PageHandler


class FakePageHandler:
    def __init__(self, tmp_path, base_url, uri):
        (tmp_path / "index.html").write_text("<html><head></head></html>")
        self.settings = {"serverapp": SimpleNamespace(base_url=base_url, ui_path=tmp_path)}
        url = urlsplit(uri)
        self.request = SimpleNamespace(path=url.path, query=url.query, cookies={})
        self.current_user = None
        self.xsrf_token = b"token"
        self.redirect = Mock()
        self.set_cookie = Mock()
        self.set_header = Mock()
        self.write = Mock()

    def get_query_argument(self, name, default=None):
        return parse_qs(self.request.query, keep_blank_values=True).get(name, [default])[-1]

    def get_env(self):
        return {}


@pytest.mark.asyncio
async def test_session_in_prefixed_base_url(tmp_path):
    handler = FakePageHandler(tmp_path, "/beaker/session/path-id/", "/beaker/session/path-id/")
    await PageHandler.get(handler, "")
    html = handler.write.call_args.args[0]
    config = json.loads(html.split('type="application/json">')[1].split('</script>')[0])
    assert config["sessionId"] == "path-id"
    assert config["sessionInPath"] is True
    handler.redirect.assert_not_called()


@pytest.mark.asyncio
async def test_path_session_removes_conflicting_query(tmp_path):
    handler = FakePageHandler(
        tmp_path, "/beaker/session/path-id/", "/beaker/session/path-id/integrations?session=other&selected=foo"
    )
    await PageHandler.get(handler, "integrations")
    handler.redirect.assert_called_once_with("/beaker/session/path-id/integrations?selected=foo")


@pytest.mark.asyncio
async def test_query_session_and_generated_session(tmp_path):
    handler = FakePageHandler(tmp_path, "/beaker/", "/beaker/?session=query-id")
    await PageHandler.get(handler, "")
    html = handler.write.call_args.args[0]
    config = json.loads(html.split('type="application/json">')[1].split('</script>')[0])
    assert config["sessionId"] == "query-id"
    assert config["sessionInPath"] is False

    handler = FakePageHandler(tmp_path, "/beaker/", "/beaker/integrations?selected=foo&session=")
    await PageHandler.get(handler, "integrations")
    redirect = urlsplit(handler.redirect.call_args.args[0])
    assert redirect.path == "/beaker/integrations"
    query = parse_qs(redirect.query)
    assert query["selected"] == ["foo"]
    assert len(query["session"]) == 1
    assert query["session"][0]
