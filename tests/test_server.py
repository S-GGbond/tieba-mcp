from __future__ import annotations

import json
from pathlib import Path

import server
from tieba.config import Settings

FIXTURES = Path(__file__).parent / "fixtures"


def _html(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class FakeClient:
    def __init__(self) -> None:
        self.settings = Settings(max_items=50)

    def search_page(self, keyword: str, page: int = 1, forum: str = "") -> str:
        return _html("search.html")

    def search_url(self, keyword: str, page: int = 1, forum: str = "") -> str:
        return f"https://tieba.baidu.com/f/search/res?qw={keyword}&pn={page}"

    def forum_page(self, forum: str, page: int = 1) -> str:
        return _html("forum.html")

    def forum_info_page(self, forum: str) -> str:
        return _html("forum.html")

    def thread_page(self, tid: int, page: int = 1) -> str:
        return _html("thread.html")

    def home_page(self) -> str:
        return _html("home.html")



def install(monkeypatch, fake=None) -> FakeClient:
    fake = fake or FakeClient()
    monkeypatch.setattr(server, "get_client", lambda: fake)
    return fake


def test_search_tool(monkeypatch):
    install(monkeypatch)
    payload = json.loads(server.tieba_search("python"))
    assert payload["ok"] is True
    assert payload["data"]["results"][0]["tid"] == 1001
    assert payload["data"]["keyword"] == "python"


def test_search_tool_rejects_empty(monkeypatch):
    install(monkeypatch)
    payload = json.loads(server.tieba_search("  "))
    assert payload["ok"] is False
    assert payload["error"]["code"] == "invalid_argument"


def test_forum_threads_tool(monkeypatch):
    install(monkeypatch)
    payload = json.loads(server.tieba_forum_threads("python", page=2))
    assert payload["ok"] is True
    assert len(payload["data"]["threads"]) == 2
    assert "pn=50" in payload["data"]["url"]


def test_thread_tool_accepts_url(monkeypatch):
    install(monkeypatch)
    payload = json.loads(server.tieba_thread("https://tieba.baidu.com/p/555"))
    assert payload["ok"] is True
    assert payload["data"]["tid"] == 555
    assert payload["data"]["title"] == "Python 入门求指导"
    assert len(payload["data"]["floors"]) == 2


def test_thread_tool_rejects_invalid(monkeypatch):
    install(monkeypatch)
    payload = json.loads(server.tieba_thread("not-a-thread"))
    assert payload["ok"] is False
    assert payload["error"]["code"] == "invalid_argument"


def test_forum_info_tool(monkeypatch):
    install(monkeypatch)
    payload = json.loads(server.tieba_forum_info("python"))
    assert payload["ok"] is True
    assert payload["data"]["followers"] == 123456


def test_home_threads_tool(monkeypatch):
    install(monkeypatch)
    payload = json.loads(server.tieba_home_threads())
    assert payload["ok"] is True
    assert payload["data"]["source"] == "home"
    assert [item["tid"] for item in payload["data"]["threads"]] == [9001, 9002]
    assert payload["data"]["forums"][0]["forum"] == "python"
    assert [item["keyword"] for item in payload["data"]["keywords"]] == ["AI 热搜"]


def test_home_threads_empty_note(monkeypatch):
    class EmptyClient(FakeClient):
        def home_page(self) -> str:
            return "<html><body></body></html>"

    install(monkeypatch, EmptyClient())
    payload = json.loads(server.tieba_home_threads())
    assert payload["ok"] is True
    assert payload["data"]["threads"] == []
    assert "note" in payload["data"]


def test_diagnose_tool(monkeypatch):
    install(monkeypatch)
    payload = json.loads(server.tieba_diagnose())
    assert payload["ok"] is True
    assert payload["data"]["accessible"] is True
    assert payload["data"]["parsed_threads"] == 2