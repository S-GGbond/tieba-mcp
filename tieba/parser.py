from __future__ import annotations

import html as html_lib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from bs4 import BeautifulSoup, Tag

CST = timezone(timedelta(hours=8))
TID_RE = re.compile(r"/p/(\d+)")
INT_RE = re.compile(r"[\d,]+")


def _soup(markup: str) -> BeautifulSoup:
    try:
        return BeautifulSoup(markup, "lxml")
    except Exception:
        return BeautifulSoup(markup, "html.parser")


def _text(node: Any, separator: str = "\n") -> str:
    if not isinstance(node, Tag):
        return ""
    for br in node.find_all("br"):
        br.replace_with("\n")
    text = node.get_text(separator, strip=True)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _loads_field(value: Any) -> dict:
    if not isinstance(value, str) or not value.strip():
        return {}
    candidates = [value, html_lib.unescape(value)]
    for candidate in candidates:
        try:
            loaded = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(loaded, dict):
            return loaded
    return {}


def _int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    match = INT_RE.search(str(value))
    if not match:
        return None
    try:
        return int(match.group(0).replace(",", ""))
    except ValueError:
        return None


def _format_time(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        stamp = float(value)
        if stamp > 10_000_000_000:
            stamp /= 1000.0
        try:
            return datetime.fromtimestamp(stamp, CST).strftime("%Y-%m-%d %H:%M")
        except (OverflowError, OSError, ValueError):
            return str(value)
    text = str(value).strip()
    if re.fullmatch(r"\d{9,13}", text):
        return _format_time(int(text))
    return text or None


def _first(node: Any, selectors: list[str]) -> Tag | None:
    if not isinstance(node, Tag):
        return None
    for selector in selectors:
        found = node.select_one(selector)
        if isinstance(found, Tag):
            return found
    return None


def _href_tid(node: Any) -> int | None:
    if not isinstance(node, Tag):
        return None
    href = node.get("href") or ""
    match = TID_RE.search(href)
    return int(match.group(1)) if match else None


def _has_next(soup: BeautifulSoup) -> bool:
    for selector in ("a.pager_next", "a.next", "a[href*='pn=']"):
        for node in soup.select(selector):
            classes = node.get("class") or []
            label = _text(node)
            if any("dis" in item for item in classes):
                continue
            if label in {"下一页", "下页", ">", "›"}:
                return True
    return False


def extract_tid(value: str) -> int | None:
    text = str(value or "").strip()
    if text.isdigit():
        return int(text)
    match = TID_RE.search(text)
    if match:
        return int(match.group(1))
    match = re.search(r"(?:^|\b)tid=(\d+)", text)
    if match:
        return int(match.group(1))
    return None


def parse_forum_threads(markup: str, limit: int = 50) -> dict:
    soup = _soup(markup)
    items = (
        soup.select("li.j_thread_list")
        or soup.select("li.thread_item_box")
        or soup.select("li[data-field]")
    )
    threads: list[dict] = []
    seen: set[int] = set()
    for item in items:
        if not isinstance(item, Tag):
            continue
        data = _loads_field(item.get("data-field"))
        anchor = _first(item, ["a.j_th_tit", "div.threadlist_title a", "a[href*='/p/']"])
        tid = _int(data.get("id")) or _href_tid(anchor)
        if not tid or tid in seen:
            continue
        seen.add(tid)
        title = (anchor.get("title") if isinstance(anchor, Tag) else None) or _text(anchor)
        author_node = _first(item, ["div.threadlist_author a", "a.frs-author-name"])
        author = data.get("author_name") or (_text(author_node) if author_node else None)
        if not author:
            badge = _first(item, ["span.tb_icon_author", "span.tb_icon_author_rely"])
            label = (badge.get("title") if isinstance(badge, Tag) else "") or ""
            author = label.split(":", 1)[-1].strip() or label.split("：", 1)[-1].strip() or None
        reply_node = _first(item, ["div.threadlist_rep_num", "span.threadlist_rep_num"])
        replies = _int(data.get("reply_num"))
        if replies is None:
            replies = _int(_text(reply_node))
        time_node = _first(item, ["span.threadlist_reply_date", "span.threadlist_reply_date_icon"])
        last_time = _format_time(data.get("last_time")) or _format_time(_text(time_node))
        abstract_node = _first(item, ["div.threadlist_abs", "div.threadlist_abs_onlyline"])
        threads.append(
            {
                "tid": tid,
                "title": title or None,
                "author": author or None,
                "reply_count": replies,
                "last_reply_time": last_time,
                "is_top": bool(data.get("is_top")),
                "is_good": bool(data.get("is_good")),
                "abstract": _text(abstract_node) or None,
                "url": f"https://tieba.baidu.com/p/{tid}",
            }
        )
        if len(threads) >= limit:
            break
    return {"threads": threads, "has_next": _has_next(soup)}


def _parse_floor(post: Tag, include_comments: bool) -> dict | None:
    data = _loads_field(post.get("data-field"))
    content = data.get("content") if isinstance(data.get("content"), dict) else {}
    author = data.get("author") if isinstance(data.get("author"), dict) else {}
    body = _first(
        post,
        [
            "div.d_post_content",
            "div.j_d_post_content",
            "div.p_content",
            "div.post_content",
        ],
    )
    text = _text(body)
    images: list[str] = []
    if isinstance(body, Tag):
        for image in body.select("img"):
            src = image.get("src") or image.get("data-original") or ""
            if src and not src.startswith("data:"):
                images.append(src)
    author_name = (
        author.get("user_name")
        or content.get("user_name")
        or _text(_first(post, ["a.p_author_name", "a.p_author"]))
        or None
    )
    if author.get("is_anonym") or content.get("is_anonym"):
        author_name = author_name or "匿名用户"
    post_no = _int(content.get("post_no"))
    if post_no is None:
        tail = _first(post, ["div.post-tail-wrap", "span.post-tail-wrap"])
        match = re.search(r"(\d+)\s*楼", _text(tail))
        post_no = int(match.group(1)) if match else None
    if not text and not images:
        return None
    floor: dict = {
        "floor": post_no,
        "author": author_name,
        "content": text,
        "images": images,
        "time": _format_time(content.get("date") or content.get("create_time")),
        "is_op": post_no == 1,
        "url": f"https://tieba.baidu.com/p/{content.get('post_id')}" if content.get("post_id") else None,
    }
    if include_comments:
        comments: list[dict] = []
        for item in post.select("li.lzl_single_post, div.lzl_single_post"):
            item_data = _loads_field(item.get("data-field"))
            item_author = item_data.get("author") if isinstance(item_data.get("author"), dict) else {}
            item_content = item_data.get("content") if isinstance(item_data.get("content"), dict) else {}
            item_text = item_content.get("text") or _text(_first(item, ["div.lzl_content", "span.lzl_content"]))
            if not item_text:
                continue
            comments.append({"author": item_author.get("user_name"), "content": item_text})
        if comments:
            floor["comments"] = comments
    return floor


def parse_thread(markup: str, max_floors: int = 50, include_comments: bool = False) -> dict:
    soup = _soup(markup)
    title_node = _first(soup, ["h1.core_title_txt", "div.core_title_txt", "span.core_title_txt"])
    title = None
    if isinstance(title_node, Tag):
        title = (title_node.get("title") or "").strip() or _text(title_node) or None
    if not title:
        doc_title = _text(soup.title)
        title = re.sub(r"[_-]百度贴吧.*$", "", doc_title).strip() or None
    floors: list[dict] = []
    for post in soup.select("div.l_post"):
        if not isinstance(post, Tag):
            continue
        floor = _parse_floor(post, include_comments)
        if floor is None:
            continue
        floors.append(floor)
        if len(floors) >= max_floors:
            break
    pager = soup.select("li.l_pager a, div.l_pager a, div.pager a")
    page_count = None
    for node in pager:
        match = re.fullmatch(r"\s*(\d+)\s*", _text(node))
        if match:
            page_count = max(page_count or 0, int(match.group(1)))
    return {
        "title": title,
        "floors": floors,
        "has_next": _has_next(soup),
        "page_count": page_count,
    }


def parse_search(markup: str, limit: int = 30) -> dict:
    soup = _soup(markup)
    results: list[dict] = []
    seen: set[int] = set()
    for block in soup.select("div.s_post, div.s_post_lz"):
        if not isinstance(block, Tag):
            continue
        anchor = _first(block, ["a.p_title", "a[href*='/p/']"])
        tid = _href_tid(anchor)
        if not tid or tid in seen:
            continue
        seen.add(tid)
        title = (anchor.get("title") if isinstance(anchor, Tag) else None) or _text(anchor)
        summary = _text(_first(block, ["div.p_content", "div.s_post_content", "p.p_content"]))
        forum = _text(_first(block, ["a.p_violet", "span.p_green", "a.p_forum"]))
        author = _text(_first(block, ["a.p_author", "span.p_author", "a.p_green"]))
        date = _text(_first(block, ["span.p_date", "span.p_time", "span.p_reply_time"]))
        results.append(
            {
                "tid": tid,
                "title": title or None,
                "forum": forum or None,
                "author": author or None,
                "summary": summary or None,
                "date": date or None,
                "url": f"https://tieba.baidu.com/p/{tid}",
            }
        )
        if len(results) >= limit:
            break
    if not results:
        for anchor in soup.select("a[href*='/p/']"):
            tid = _href_tid(anchor)
            title = _text(anchor)
            if not tid or tid in seen or not title or len(title) < 2:
                continue
            seen.add(tid)
            results.append(
                {
                    "tid": tid,
                    "title": title,
                    "forum": None,
                    "author": None,
                    "summary": None,
                    "date": None,
                    "url": f"https://tieba.baidu.com/p/{tid}",
                }
            )
            if len(results) >= limit:
                break
    return {"results": results, "has_next": _has_next(soup)}


JUNK_TITLES = {
    "回复",
    "赞",
    "分享",
    "收藏",
    "只看楼主",
    "下一页",
    "上一页",
    "首页",
    "贴吧",
    "更多",
    "登录",
    "注册",
}


def _absolute(href: str) -> str:
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return f"https://tieba.baidu.com{href}"
    return href


def _forum_from_href(href: str) -> str | None:
    try:
        query = parse_qs(urlparse(href).query)
    except ValueError:
        return None
    names = query.get("kw")
    if not names:
        return None
    value = unquote(names[0]).strip()
    return value or None


def _valid_title(text: str) -> bool:
    if not text or len(text) < 2 or len(text) > 120:
        return False
    if text in JUNK_TITLES:
        return False
    return re.fullmatch(r"[\d\s\.,，。万+%‰-]+", text) is None


def parse_home_threads(markup: str, limit: int = 50) -> dict:
    soup = _soup(markup)
    containers = soup.select(
        "div.recommend_list, ul.recommend_list, div.recommend_content, "
        "div.hot_thread_list, div.index_recommend, div.recommend_item"
    )
    anchors: list[Tag] = []
    for container in containers:
        anchors.extend(container.select("a[href*='/p/']"))
    if not anchors:
        anchors = soup.select("a[href*='/p/']")

    threads: list[dict] = []
    seen: set[int] = set()
    for anchor in anchors:
        tid = _href_tid(anchor)
        if not tid or tid in seen:
            continue
        title = ((anchor.get("title") or "").strip() or _text(anchor))
        if not _valid_title(title):
            continue
        seen.add(tid)
        scope = anchor.find_parent(["li", "div"]) or anchor.parent
        forum = None
        summary = None
        author = None
        if isinstance(scope, Tag):
            forum_node = _first(scope, ["a.p_forum", "a[href*='/f?kw=']"])
            if isinstance(forum_node, Tag):
                forum = _text(forum_node) or _forum_from_href(forum_node.get("href") or "") or None
            summary = _text(
                _first(scope, ["div.recommend_abstract", "div.threadlist_abs", "div.recommend_desc"])
            ) or None
            author = _text(_first(scope, ["a.p_author", "span.p_author_name", "a.frs-author-name"])) or None
        threads.append(
            {
                "tid": tid,
                "title": title,
                "forum": forum,
                "author": author,
                "summary": summary,
                "url": f"https://tieba.baidu.com/p/{tid}",
            }
        )
        if len(threads) >= limit:
            break

    forums: list[dict] = []
    seen_forums: set[str] = set()
    for anchor in soup.select("a[href*='kw=']"):
        href = anchor.get("href") or ""
        if "/p/" in href or "/f/search" in href:
            continue
        name = _forum_from_href(href)
        if not name or name in seen_forums:
            continue
        seen_forums.add(name)
        forums.append(
            {
                "forum": name,
                "title": _text(anchor) or f"{name}吧",
                "url": _absolute(href),
            }
        )
        if len(forums) >= 20:
            break

    return {
        "threads": threads,
        "forums": forums,
        "keywords": _collect_keywords(soup, limit),
        "has_next": False,
    }


def _collect_keywords(soup: BeautifulSoup, limit: int) -> list[dict]:
    nodes: list[Tag] = []
    for item in soup.select(
        "div.hotsearch-item, li.hotsearch-item, div.HotSearch-item, div.hot-item, div.hot-list-item"
    ):
        nodes.extend(item.select("a"))
    if not nodes:
        nodes = soup.select("a[href*='qw=']")

    keywords: list[dict] = []
    seen: set[str] = set()
    for anchor in nodes:
        text = _text(anchor)
        href = anchor.get("href") or ""
        if "/p/" in href or not _valid_title(text) or text in seen:
            continue
        seen.add(text)
        keywords.append({"keyword": text, "url": _absolute(href)})
        if len(keywords) >= limit:
            break
    return keywords


def parse_forum_info(markup: str, forum: str) -> dict:
    soup = _soup(markup)
    followers = _int(_text(_first(soup, ["div.card_infoNum", "span.card_infoNum"])))
    threads = _int(_text(_first(soup, ["div.card_menNum", "span.card_menNum"])))
    intro_node = _first(soup, ["div.card_rsm", "div.card_intro", "p.card_rsm"])
    intro = _text(intro_node) or None
    if followers is None or threads is None:
        text = soup.get_text(" ", strip=True)
        if threads is None:
            match = re.search(r"(\d[\d,]*)\s*个?贴子", text)
            threads = _int(match.group(1)) if match else None
        if followers is None:
            match = re.search(r"(\d[\d,]*)\s*人关注", text)
            followers = _int(match.group(1)) if match else None
    return {
        "forum": forum,
        "followers": followers,
        "thread_count": threads,
        "intro": intro,
        "url": f"https://tieba.baidu.com/f?kw={forum}",
    }