from __future__ import annotations

import httpx
import pytest

from tieba.config import Settings
from tieba.errors import AccessDenied, VerificationRequired
from tieba.http_client import TiebaClient


def make_client(handler, **overrides) -> TiebaClient:
    settings = Settings(delay=0, timeout=3, **overrides)
    return TiebaClient(settings, transport=httpx.MockTransport(handler))


def test_forum_page_and_cookie(fixture_html):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["cookie"] = request.headers.get("cookie")
        return httpx.Response(200, text=fixture_html("forum.html"))

    client = make_client(handler, cookie="BDUSS=token")
    markup = client.forum_page("python", 2)
    assert "j_thread_list" in markup
    assert captured["url"].startswith("https://tieba.baidu.com/f?")
    assert "kw=python" in captured["url"]
    assert "pn=50" in captured["url"]
    assert captured["cookie"] == "BDUSS=token"


def test_verification_raises(fixture_html):
    client = make_client(lambda request: httpx.Response(403, text=fixture_html("verify.html")))
    with pytest.raises(VerificationRequired) as excinfo:
        client.forum_page("python")
    assert "安全验证" in excinfo.value.message
    assert "TIEBA_COOKIE" in excinfo.value.hint


def test_not_found(fixture_html):
    client = make_client(lambda request: httpx.Response(404, text="<html>not found</html>"))
    with pytest.raises(AccessDenied) as excinfo:
        client.thread_page(1)
    assert excinfo.value.extra.get("status") == 404


def test_thread_page_url():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, text="<html></html>")

    client = make_client(handler)
    client.thread_page(123, page=3)
    assert "/p/123" in captured["url"]
    assert "pn=3" in captured["url"]


def test_search_page_with_forum():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, text="<html></html>")

    client = make_client(handler)
    client.search_page("asyncio", page=2, forum="python")
    assert "/f/search/res" in captured["url"]
    assert "qw=asyncio" in captured["url"]
    assert "kw=python" in captured["url"]
    assert "pn=2" in captured["url"]


def test_search_url_is_public():
    client = make_client(lambda request: httpx.Response(200, text=""))
    url = client.search_url("异步 编程", page=1, forum="python")
    assert url.startswith("https://tieba.baidu.com/f/search/res?")
    assert "python" in url


def test_debug_dump(tmp_path, fixture_html):
    target = tmp_path / "dump"
    client = make_client(
        lambda request: httpx.Response(200, text=fixture_html("forum.html")),
        debug_dump=str(target),
    )
    client.forum_page("python")
    files = list(target.glob("tieba-dump-*.html"))
    assert len(files) == 1
    assert "j_thread_list" in files[0].read_text(encoding="utf-8")