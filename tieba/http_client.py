from __future__ import annotations

import logging
import time
from pathlib import Path
from urllib.parse import quote

import httpx

from .browser import BrowserFetcher
from .config import Settings, load_settings
from .detect import looks_like_verification
from .errors import AccessDenied, NetworkFailure, VerificationRequired

LOG = logging.getLogger("tieba-mcp.http")

BASE = "https://tieba.baidu.com"
FORUM_PAGE_SIZE = 50


def _decode(response: httpx.Response) -> str:
    charset = response.charset_encoding
    if charset:
        try:
            return response.content.decode(charset, errors="replace")
        except LookupError:
            pass
    raw = response.content
    for encoding in ("utf-8", "gb18030"):
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        if text.count("\ufffd") <= 2:
            return text
    return raw.decode("utf-8", errors="replace")


class TiebaClient:
    def __init__(
        self,
        settings: Settings | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.settings = settings or load_settings()
        self._http = httpx.Client(
            follow_redirects=True,
            timeout=self.settings.timeout,
            transport=transport,
            headers={
                "User-Agent": self.settings.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
                "Referer": self.settings.referer,
            },
        )
        self._browser: BrowserFetcher | None = None
        self._last_request = 0.0
        self._counter = 0

    def _throttle(self) -> None:
        gap = self.settings.delay
        if gap <= 0:
            return
        wait = self._last_request + gap - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def _dump(self, markup: str) -> None:
        if not self.settings.debug_dump:
            return
        self._counter += 1
        target = Path(self.settings.debug_dump).expanduser()
        if target.is_dir() or not target.suffix:
            target.mkdir(parents=True, exist_ok=True)
            target = target / f"tieba-dump-{int(time.time())}-{self._counter}.html"
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(markup, encoding="utf-8")
        LOG.info("页面已保存到 %s", target)

    def _get(self, url: str, params: dict | None = None) -> str:
        if self.settings.backend == "browser":
            if params:
                url = str(httpx.URL(url, params=params))
            if self._browser is None:
                self._browser = BrowserFetcher(self.settings)
            self._throttle()
            markup = self._browser.fetch(url)
            self._dump(markup)
            return markup

        headers = {}
        cookie = self.settings.effective_cookie()
        if cookie:
            headers["Cookie"] = cookie
        last_error: Exception | None = None
        for attempt in range(2):
            self._throttle()
            try:
                response = self._http.get(url, params=params, headers=headers)
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt == 0:
                    time.sleep(1.5)
                    continue
                raise NetworkFailure(
                    f"请求贴吧失败: {exc}", hint="检查网络或代理设置，必要时调大 TIEBA_TIMEOUT"
                ) from exc
            markup = _decode(response)
            self._dump(markup)
            if looks_like_verification(response.status_code, markup, str(response.url)):
                raise VerificationRequired(
                    "贴吧返回了安全验证页，当前 IP 或未登录状态被风控",
                    hint=(
                        "在 config.json 或环境变量 TIEBA_COOKIE 中填入浏览器里 tieba.baidu.com 的 Cookie"
                        "（至少包含 BDUSS），或把 TIEBA_BACKEND 设为 browser 并手动过验证"
                    ),
                    status=response.status_code,
                )
            if response.status_code == 404:
                raise AccessDenied("页面不存在", hint="检查 tid/吧名是否正确", status=404)
            if response.status_code >= 500 and attempt == 0:
                time.sleep(2.0)
                continue
            if response.status_code >= 400:
                raise AccessDenied(
                    f"贴吧返回 HTTP {response.status_code}",
                    hint="稍后重试；持续失败通常是触发风控",
                    status=response.status_code,
                )
            return markup
        raise NetworkFailure(f"请求贴吧失败: {last_error}")

    def forum_url(self, forum: str, page: int = 1) -> tuple[str, dict]:
        page = max(1, page)
        return f"{BASE}/f", {"kw": forum.strip(), "ie": "utf-8", "pn": (page - 1) * FORUM_PAGE_SIZE}

    def forum_page(self, forum: str, page: int = 1) -> str:
        url, params = self.forum_url(forum, page)
        return self._get(url, params)

    def forum_info_page(self, forum: str) -> str:
        return self.forum_page(forum, 1)

    def home_page(self) -> str:
        return self._get(f"{BASE}/")


    def thread_page(self, tid: int, page: int = 1) -> str:
        page = max(1, page)
        return self._get(f"{BASE}/p/{tid}", {"pn": page})

    def search_page(self, keyword: str, page: int = 1, forum: str = "") -> str:
        page = max(1, page)
        params = {"ie": "utf-8", "qw": keyword.strip(), "pn": page}
        if forum.strip():
            params["kw"] = forum.strip()
        return self._get(f"{BASE}/f/search/res", params)

    def search_url(self, keyword: str, page: int = 1, forum: str = "") -> str:
        params = {"ie": "utf-8", "qw": quote(keyword.strip()), "pn": page}
        if forum.strip():
            params["kw"] = quote(forum.strip())
        query = "&".join(f"{key}={value}" for key, value in params.items())
        return f"{BASE}/f/search/res?{query}"

    def close(self) -> None:
        self._http.close()
        if self._browser is not None:
            self._browser.close()
            self._browser = None