from __future__ import annotations

import logging
import time

from .config import Settings
from .detect import looks_like_verification
from .errors import NetworkFailure, VerificationRequired

LOG = logging.getLogger("tieba-mcp.browser")


class BrowserFetcher:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._playwright = None
        self._browser = None
        self._context = None

    def _cookie_list(self) -> list[dict]:
        cookie = self.settings.effective_cookie()
        items = []
        for chunk in cookie.split(";"):
            if "=" not in chunk:
                continue
            name, value = chunk.split("=", 1)
            name = name.strip()
            if not name:
                continue
            items.append(
                {
                    "name": name,
                    "value": value.strip(),
                    "domain": ".baidu.com",
                    "path": "/",
                }
            )
        return items

    def _ensure(self) -> None:
        if self._context is not None:
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise NetworkFailure(
                "浏览器后端需要 playwright",
                hint="pip install playwright 并确保系统已安装 Chrome",
            ) from exc
        self._playwright = sync_playwright().start()
        launch_args = ["--disable-blink-features=AutomationControlled"]
        kwargs = {
            "channel": "chrome",
            "headless": self.settings.headless,
            "args": launch_args,
            "locale": "zh-CN",
            "user_agent": self.settings.user_agent,
        }
        if self.settings.profile_dir:
            self._context = self._playwright.chromium.launch_persistent_context(
                self.settings.profile_dir, **kwargs
            )
        else:
            self._browser = self._playwright.chromium.launch(
                channel="chrome",
                headless=self.settings.headless,
                args=launch_args,
            )
            self._context = self._browser.new_context(
                locale="zh-CN", user_agent=self.settings.user_agent
            )
        cookies = self._cookie_list()
        if cookies:
            self._context.add_cookies(cookies)

    def fetch(self, url: str) -> str:
        self._ensure()
        page = self._context.new_page()
        try:
            response = page.goto(
                url, wait_until="domcontentloaded", timeout=int(self.settings.timeout * 1000)
            )
            status = response.status if response else 0
            markup = page.content()
            if looks_like_verification(status, markup, page.url):
                markup = self._wait_for_human(page, status)
            return markup
        except NetworkFailure:
            raise
        except Exception as exc:
            raise NetworkFailure(f"浏览器打开页面失败: {exc}") from exc
        finally:
            try:
                page.close()
            except Exception:
                pass

    def _wait_for_human(self, page, status: int) -> str:
        if self.settings.headless or self.settings.verify_wait <= 0:
            raise VerificationRequired(
                "贴吧返回了安全验证页，需要人工完成验证",
                hint="把 TIEBA_BACKEND 设为 browser 且 TIEBA_HEADLESS=false，或配置有效的 TIEBA_COOKIE",
            )
        LOG.info("检测到验证页，等待人工完成验证，最长 %.0f 秒", self.settings.verify_wait)
        deadline = time.time() + self.settings.verify_wait
        while time.time() < deadline:
            page.wait_for_timeout(1000)
            markup = page.content()
            current_status = 200
            if not looks_like_verification(current_status, markup, page.url):
                return markup
        raise VerificationRequired(
            "等待人工验证超时",
            hint="在浏览器窗口完成滑块/登录后重试，或配置有效的 TIEBA_COOKIE",
        )

    def close(self) -> None:
        for target in (self._context, self._browser):
            if target is not None:
                try:
                    target.close()
                except Exception:
                    pass
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
        self._context = None
        self._browser = None
        self._playwright = None