from __future__ import annotations

import json
import os
from dataclasses import dataclass, fields
from pathlib import Path

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"

ENV_KEYS = {
    "cookie": "TIEBA_COOKIE",
    "bduss": "TIEBA_BDUSS",
    "user_agent": "TIEBA_USER_AGENT",
    "timeout": "TIEBA_TIMEOUT",
    "delay": "TIEBA_DELAY",
    "backend": "TIEBA_BACKEND",
    "headless": "TIEBA_HEADLESS",
    "profile_dir": "TIEBA_PROFILE_DIR",
    "max_items": "TIEBA_MAX_ITEMS",
    "debug_dump": "TIEBA_DEBUG_DUMP",
    "verify_wait": "TIEBA_VERIFY_WAIT",
    "referer": "TIEBA_REFERER",
}


@dataclass(frozen=True)
class Settings:
    cookie: str = ""
    bduss: str = ""
    user_agent: str = DEFAULT_USER_AGENT
    timeout: float = 20.0
    delay: float = 1.5
    backend: str = "http"
    headless: bool = False
    profile_dir: str = ""
    max_items: int = 50
    debug_dump: str = ""
    verify_wait: float = 120.0
    referer: str = "https://tieba.baidu.com/"

    def effective_cookie(self) -> str:
        if self.cookie.strip():
            return self.cookie.strip()
        if self.bduss.strip():
            return f"BDUSS={self.bduss.strip()}"
        return ""

    def masked(self) -> dict:
        cookie = self.effective_cookie()
        summary = {}
        for chunk in cookie.split(";"):
            if "=" not in chunk:
                continue
            key, value = chunk.split("=", 1)
            key = key.strip()
            if not key:
                continue
            summary[key] = "***" if value.strip() else ""
        return {
            "backend": self.backend,
            "headless": self.headless,
            "timeout": self.timeout,
            "delay": self.delay,
            "max_items": self.max_items,
            "cookie_keys": sorted(summary),
            "has_cookie": bool(cookie),
            "profile_dir": self.profile_dir or None,
            "debug_dump": self.debug_dump or None,
        }


def _as_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on", "y"}:
        return True
    if text in {"0", "false", "no", "off", "n"}:
        return False
    return default


def _as_float(value: object, default: float) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def _as_int(value: object, default: int) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _coerce(key: str, value: object, default: object) -> object:
    if key in {"headless"}:
        return _as_bool(value, bool(default))
    if key in {"timeout", "delay", "verify_wait"}:
        return _as_float(value, float(default))
    if key in {"max_items"}:
        return _as_int(value, int(default))
    return str(value) if value is not None else default


def config_path() -> Path:
    override = os.environ.get("TIEBA_CONFIG", "").strip()
    return Path(override).expanduser() if override else DEFAULT_CONFIG_PATH


def load_settings(path: Path | None = None) -> Settings:
    target = path or config_path()
    raw: dict = {}
    if target.is_file():
        try:
            loaded = json.loads(target.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                raw = loaded
        except (OSError, ValueError):
            raw = {}

    known = {item.name: item.default for item in fields(Settings)}
    values = {}
    for key, default in known.items():
        if key in raw:
            values[key] = _coerce(key, raw[key], default)
        else:
            values[key] = default

    for key, env_name in ENV_KEYS.items():
        env_value = os.environ.get(env_name)
        if env_value is None or env_value.strip() == "":
            continue
        values[key] = _coerce(key, env_value, known[key])

    values["backend"] = values["backend"].strip().lower()
    if values["backend"] not in {"http", "browser"}:
        values["backend"] = "http"
    values["max_items"] = max(1, min(values["max_items"], 200))
    values["delay"] = max(0.0, min(values["delay"], 30.0))
    values["timeout"] = max(3.0, min(values["timeout"], 120.0))
    values["verify_wait"] = max(0.0, min(values["verify_wait"], 600.0))
    return Settings(**values)