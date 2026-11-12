from __future__ import annotations

from pathlib import Path

from tieba.config import Settings, load_settings
from tieba.detect import looks_like_verification


def test_looks_like_verification(fixture_html):
    assert looks_like_verification(403, fixture_html("verify.html")) is True
    assert looks_like_verification(200, "<html>python 吧</html>") is False
    assert looks_like_verification(403, "<html>forbidden</html>") is True
    assert looks_like_verification(403, "<html>tieba</html>") is False
    assert looks_like_verification(200, "", "https://wappass.baidu.com/x") is True


def test_defaults_without_config(tmp_path, monkeypatch):
    missing = tmp_path / "missing.json"
    monkeypatch.setenv("TIEBA_CONFIG", str(missing))
    settings = load_settings()
    assert settings.backend == "http"
    assert settings.delay == 1.5
    assert settings.effective_cookie() == ""


def test_config_file(tmp_path):
    config = tmp_path / "config.json"
    config.write_text(
        '{"cookie": "BDUSS=abc", "backend": "browser", "headless": true, "delay": 0.5}',
        encoding="utf-8",
    )
    settings = load_settings(config)
    assert settings.backend == "browser"
    assert settings.headless is True
    assert settings.delay == 0.5
    assert settings.effective_cookie() == "BDUSS=abc"


def test_env_overrides_config(tmp_path, monkeypatch):
    config = tmp_path / "config.json"
    config.write_text('{"backend": "browser", "delay": 3}', encoding="utf-8")
    monkeypatch.setenv("TIEBA_BACKEND", "http")
    monkeypatch.setenv("TIEBA_DELAY", "0.2")
    monkeypatch.setenv("TIEBA_MAX_ITEMS", "999")
    settings = load_settings(config)
    assert settings.backend == "http"
    assert settings.delay == 0.2
    assert settings.max_items == 200


def test_bduss_becomes_cookie(monkeypatch):
    monkeypatch.setenv("TIEBA_BDUSS", "xyz")
    monkeypatch.delenv("TIEBA_COOKIE", raising=False)
    settings = load_settings(Path("/nonexistent/config.json"))
    assert settings.effective_cookie() == "BDUSS=xyz"


def test_invalid_backend_falls_back(tmp_path):
    config = tmp_path / "config.json"
    config.write_text('{"backend": "curl"}', encoding="utf-8")
    assert load_settings(config).backend == "http"


def test_coerce_helpers():
    from tieba.config import _coerce

    assert _coerce("headless", "yes", False) is True
    assert _coerce("delay", "1.25", 0.0) == 1.25
    assert _coerce("max_items", "12.9", 0) == 12


def test_masked_hides_values():
    settings = Settings(cookie="BDUSS=secret; STOKEN=other")
    masked = settings.masked()
    assert masked["has_cookie"] is True
    assert masked["cookie_keys"] == ["BDUSS", "STOKEN"]
    assert "secret" not in str(masked)