from __future__ import annotations

from tieba.parser import (
    extract_tid,
    parse_forum_info,
    parse_forum_threads,
    parse_home_threads,

    parse_search,
    parse_thread,
)


def test_parse_forum_threads(fixture_html):
    parsed = parse_forum_threads(fixture_html("forum.html"))
    threads = parsed["threads"]
    assert parsed["has_next"] is True
    assert len(threads) == 2
    first = threads[0]
    assert first["tid"] == 1001
    assert first["title"] == "Python 入门求指导"
    assert first["author"] == "alice"
    assert first["reply_count"] == 12
    assert first["is_good"] is True
    assert first["abstract"] == "刚学 Python，求推荐资料"
    assert first["url"] == "https://tieba.baidu.com/p/1001"
    assert threads[1]["is_top"] is True


def test_parse_forum_threads_respects_limit(fixture_html):
    parsed = parse_forum_threads(fixture_html("forum.html"), limit=1)
    assert len(parsed["threads"]) == 1


def test_parse_forum_threads_fallback_without_data_field(fixture_html):
    markup = """
    <ul>
      <li class="j_thread_list"><a class="j_th_tit" href="/p/2002">纯链接帖子</a></li>
    </ul>
    """
    parsed = parse_forum_threads(markup)
    assert parsed["threads"][0]["tid"] == 2002
    assert parsed["threads"][0]["title"] == "纯链接帖子"
    assert parsed["has_next"] is False


def test_parse_thread(fixture_html):
    parsed = parse_thread(fixture_html("thread.html"), include_comments=True)
    assert parsed["title"] == "Python 入门求指导"
    assert parsed["has_next"] is True
    assert parsed["page_count"] == 2
    assert len(parsed["floors"]) == 2
    first, second = parsed["floors"]
    assert first["floor"] == 1
    assert first["is_op"] is True
    assert first["author"] == "alice"
    assert "第一行" in first["content"] and "第二行" in first["content"]
    assert first["images"] == ["https://img.example.com/a.png"]
    assert second["floor"] == 2
    assert second["content"] == "建议先看官方教程"
    assert second["comments"] == [{"author": "alice", "content": "谢谢"}]


def test_parse_thread_without_comments(fixture_html):
    parsed = parse_thread(fixture_html("thread.html"))
    assert "comments" not in parsed["floors"][1]


def test_parse_thread_title_fallback(fixture_html):
    parsed = parse_thread("<html><head><title>某个帖子_百度贴吧</title></head><body></body></html>")
    assert parsed["title"] == "某个帖子"


def test_parse_search(fixture_html):
    parsed = parse_search(fixture_html("search.html"))
    results = parsed["results"]
    assert len(results) == 2
    assert results[0]["tid"] == 1001
    assert results[0]["forum"] == "python吧"
    assert results[0]["author"] == "alice"
    assert results[0]["summary"] == "刚学 Python，求推荐资料"
    assert results[1]["tid"] == 1003


def test_parse_search_fallback(fixture_html):
    parsed = parse_search('<div><a href="/p/3003">野链接帖子</a></div>')
    assert parsed["results"][0]["tid"] == 3003
    assert parsed["results"][0]["title"] == "野链接帖子"


def test_parse_home_threads(fixture_html):
    parsed = parse_home_threads(fixture_html("home.html"))
    threads = parsed["threads"]
    assert parsed["has_next"] is False
    assert [item["tid"] for item in threads] == [9001, 9002]
    assert threads[0]["title"] == "推荐帖 A"
    assert threads[0]["forum"] == "python吧"
    assert threads[0]["summary"] == "摘要 A"
    forums = [item["forum"] for item in parsed["forums"]]
    assert forums == ["python", "ai", "原神"]
    assert [item["keyword"] for item in parsed["keywords"]] == ["AI 热搜"]
    assert parsed["keywords"][0]["url"].startswith("https://tieba.baidu.com/f/search/res")


def test_parse_home_threads_respects_limit(fixture_html):
    parsed = parse_home_threads(fixture_html("home.html"), limit=1)
    assert len(parsed["threads"]) == 1



def test_parse_forum_info(fixture_html):
    info = parse_forum_info(fixture_html("forum.html"), "python")
    assert info["followers"] == 123456
    assert info["thread_count"] == 7890123
    assert info["intro"] == "Python 学习交流吧"
    assert info["url"] == "https://tieba.baidu.com/f?kw=python"


def test_parse_forum_info_text_fallback():
    info = parse_forum_info("<div>1,000 人关注 2,000 个贴子</div>", "demo")
    assert info["followers"] == 1000
    assert info["thread_count"] == 2000


def test_extract_tid():
    assert extract_tid("123456") == 123456
    assert extract_tid("https://tieba.baidu.com/p/987654321?pn=2") == 987654321
    assert extract_tid("https://tieba.baidu.com/p/123?tid=456") == 123
    assert extract_tid("not-a-tid") is None