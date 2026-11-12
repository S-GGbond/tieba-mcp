from __future__ import annotations

import json
import logging
import sys

from mcp.server.fastmcp import FastMCP

from tieba.config import load_settings
from tieba.errors import ParseFailure, TiebaError
from tieba.http_client import TiebaClient
from tieba.parser import (
    extract_tid,
    parse_forum_info,
    parse_forum_threads,
    parse_home_threads,

    parse_search,
    parse_thread,
)

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
LOG = logging.getLogger("tieba-mcp")

mcp = FastMCP(
    "tieba",
    instructions=(
        "只读的百度贴吧检索工具集。可以搜索帖子、读取吧内帖子列表、读取主题帖楼层、查看吧信息。"
        "所有工具都只读，不会发帖、回复、点赞或登录。访问频率受 TIEBA_DELAY 限制。"
    ),
)

_client: TiebaClient | None = None


def get_client() -> TiebaClient:
    global _client
    if _client is None:
        _client = TiebaClient(load_settings())
    return _client


def _json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _ok(tool: str, data: dict) -> str:
    return _json({"ok": True, "tool": tool, "data": data})


def _error(tool: str, exc: Exception) -> str:
    if isinstance(exc, TiebaError):
        return _json({"ok": False, "tool": tool, "error": exc.to_dict()})
    LOG.exception("工具 %s 未预期错误", tool)
    return _json(
        {
            "ok": False,
            "tool": tool,
            "error": {"code": "internal_error", "message": str(exc)},
        }
    )


def _limit(value: int) -> int:
    if value and value > 0:
        return min(int(value), 200)
    return get_client().settings.max_items


@mcp.tool()
def tieba_search(keyword: str, page: int = 1, forum: str = "", limit: int = 0) -> str:
    """在百度贴吧搜索帖子（只读）。

    返回匹配帖子的 tid、标题、所属吧、作者、摘要、日期和链接。标题/摘要可能被贴吧截断，
    需要完整内容请把 tid 传给 tieba_thread。

    Args:
        keyword: 搜索关键词。
        page: 页码，从 1 开始。
        forum: 可选，只在指定吧内搜索，例如 "python"。
        limit: 最多返回多少条，0 表示使用配置里的 TIEBA_MAX_ITEMS（默认 50，上限 200）。
    """
    if not keyword or not keyword.strip():
        return _json(
            {"ok": False, "tool": "tieba_search", "error": {"code": "invalid_argument", "message": "keyword 不能为空"}}
        )
    client = get_client()
    try:
        markup = client.search_page(keyword, page, forum)
        parsed = parse_search(markup, _limit(limit))
        parsed.update(
            {
                "keyword": keyword,
                "forum": forum or None,
                "page": max(1, page),
                "search_url": client.search_url(keyword, page, forum),
            }
        )
        if not parsed["results"]:
            parsed["note"] = "没有解析到搜索结果，可能是没有匹配内容，也可能是页面结构变化；可开启 TIEBA_DEBUG_DUMP 导出 HTML 排查"
        return _ok("tieba_search", parsed)
    except Exception as exc:
        return _error("tieba_search", exc)


@mcp.tool()
def tieba_forum_threads(forum: str, page: int = 1, limit: int = 0) -> str:
    """列出某个吧的帖子列表（只读，按贴吧默认的回复时间排序）。

    Args:
        forum: 吧名，不带“吧”字，例如 "python"、"原神"。
        page: 页码，从 1 开始；每页约 50 条。
        limit: 最多返回多少条，0 表示使用配置值。
    """
    if not forum or not forum.strip():
        return _json(
            {"ok": False, "tool": "tieba_forum_threads", "error": {"code": "invalid_argument", "message": "forum 不能为空"}}
        )
    client = get_client()
    try:
        markup = client.forum_page(forum, page)
        parsed = parse_forum_threads(markup, _limit(limit))
        parsed.update(
            {
                "forum": forum.strip(),
                "page": max(1, page),
                "url": f"https://tieba.baidu.com/f?kw={forum.strip()}&ie=utf-8&pn={(max(1, page) - 1) * 50}",
            }
        )
        if not parsed["threads"]:
            parsed["note"] = "没有解析到帖子，可能是吧名不存在或被限制访问；可开启 TIEBA_DEBUG_DUMP 排查"
        return _ok("tieba_forum_threads", parsed)
    except Exception as exc:
        return _error("tieba_forum_threads", exc)


@mcp.tool()
def tieba_thread(
    thread: str,
    page: int = 1,
    max_floors: int = 0,
    include_comments: bool = False,
) -> str:
    """读取一个主题帖的标题与楼层内容（只读）。

    Args:
        thread: 帖子 tid，或完整帖子链接，例如 "1234567890" 或 "https://tieba.baidu.com/p/1234567890"。
        page: 楼层页码，从 1 开始。
        max_floors: 最多解析多少层，0 表示使用配置值（默认 50，上限 200）。
        include_comments: 是否附带解析楼中楼评论（可能不完整）。
    """
    tid = extract_tid(thread)
    if not tid:
        return _json(
            {
                "ok": False,
                "tool": "tieba_thread",
                "error": {"code": "invalid_argument", "message": "thread 必须是 tid 或包含 /p/<tid> 的链接"},
            }
        )
    client = get_client()
    try:
        markup = client.thread_page(tid, page)
        parsed = parse_thread(markup, _limit(max_floors), include_comments)
        parsed.update(
            {
                "tid": tid,
                "page": max(1, page),
                "source_url": f"https://tieba.baidu.com/p/{tid}?pn={max(1, page)}",
            }
        )
        if not parsed["floors"]:
            raise ParseFailure(
                "页面里没有解析到楼层内容",
                hint="帖子可能被删除/仅作者可见，也可能页面结构变化；可开启 TIEBA_DEBUG_DUMP 导出 HTML",
                tid=tid,
            )
        return _ok("tieba_thread", parsed)
    except Exception as exc:
        return _error("tieba_thread", exc)


@mcp.tool()
def tieba_home_threads(limit: int = 0) -> str:
    """获取贴吧首页的推荐流帖子列表、热门吧和热搜关键词（只读）。

    首页推荐流没有稳定分页；需要翻页或多页内容请改用 tieba_forum_threads 或 tieba_search。
    未登录时首页内容可能较少，建议配置带 BDUSS 的 cookie。

    Args:
        limit: 最多返回多少条帖子/关键词，0 表示使用配置值（默认 50，上限 200）。
    """
    client = get_client()
    try:
        parsed = parse_home_threads(client.home_page(), _limit(limit))
        parsed.update({"source": "home", "url": "https://tieba.baidu.com/"})
        if not parsed["threads"] and not parsed["forums"] and not parsed["keywords"]:
            parsed["note"] = "没有解析到任何列表项，可能是未登录或页面结构变化；可开启 TIEBA_DEBUG_DUMP 导出 HTML"
        return _ok("tieba_home_threads", parsed)
    except Exception as exc:
        return _error("tieba_home_threads", exc)


@mcp.tool()
def tieba_forum_info(forum: str) -> str:
    """查看某个吧的关注人数、帖子数和简介（只读）。

    Args:
        forum: 吧名，不带“吧”字。
    """
    if not forum or not forum.strip():
        return _json(
            {"ok": False, "tool": "tieba_forum_info", "error": {"code": "invalid_argument", "message": "forum 不能为空"}}
        )
    client = get_client()
    try:
        markup = client.forum_info_page(forum)
        return _ok("tieba_forum_info", parse_forum_info(markup, forum.strip()))
    except Exception as exc:
        return _error("tieba_forum_info", exc)


@mcp.tool()
def tieba_diagnose() -> str:
    """检查贴吧 MCP 的配置与当前网络能否正常读取贴吧（只读）。

    会实际发起一次轻量请求，返回是否可用、是否触发安全验证，以及脱敏后的配置摘要。
    排查 403/验证失败时先调用它。
    """
    client = get_client()
    result = {"config": client.settings.masked(), "target": "https://tieba.baidu.com/f?kw=python"}
    try:
        markup = client.forum_page("python", 1)
        parsed = parse_forum_threads(markup, 3)
        result.update(
            {
                "accessible": True,
                "parsed_threads": len(parsed["threads"]),
                "sample": parsed["threads"],
                "message": "贴吧可正常访问",
            }
        )
    except TiebaError as exc:
        result.update({"accessible": False, "error": exc.to_dict()})
        if exc.code == "verification_required":
            result["message"] = "被百度安全验证拦截，需要配置有效 Cookie 或改用 browser 后端"
        else:
            result["message"] = "访问贴吧失败"
    except Exception as exc:
        LOG.exception("diagnose 未预期错误")
        result.update(
            {"accessible": False, "error": {"code": "internal_error", "message": str(exc)}}
        )
    return _json({"ok": True, "tool": "tieba_diagnose", "data": result})


if __name__ == "__main__":
    mcp.run()