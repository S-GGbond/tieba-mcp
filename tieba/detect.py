from __future__ import annotations

VERIFICATION_MARKERS = (
    "百度安全验证",
    "BIOC_OPTIONS",
    "wappass.baidu.com",
    "请输入验证码",
    "请完成验证",
)


def looks_like_verification(status: int, markup: str, url: str = "") -> bool:
    if url and ("wappass.baidu.com" in url or "verify" in url.lower()):
        return True
    if not markup:
        return status in {403, 429}
    if any(marker in markup for marker in VERIFICATION_MARKERS):
        return True
    return status in {403, 429} and "tieba" not in markup.lower()