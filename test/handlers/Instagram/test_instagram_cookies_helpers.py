"""Unit-тесты helper-логики Instagram cookies."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# test/handlers/Instagram/test_instagram_cookies_helpers.py -> project root это parents[3]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Минимальные env для загрузки src.config.
os.environ.setdefault("BOT_DB_PATH", str(PROJECT_ROOT / "src" / "data" / "db" / "bot.db"))
os.environ.setdefault("BOT_VERSION", "local-test")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("BOT_TOKEN", "local-test-token")
os.environ.setdefault("YANDEX_MUSIC_TOKEN", "local-test-token")
os.environ.setdefault("YOUTUBE_COOKIES_ENABLED", "false")
os.environ.setdefault("INSTAGRAM_COOKIES_ENABLED", "false")

from src.handlers.resources.Instagram import cookies as instagram_cookies


def test_instagram_cookie_opts_disabled(monkeypatch) -> None:
    """При отключенном флаге cookies не должны передаваться."""
    monkeypatch.setattr(instagram_cookies, "INSTAGRAM_COOKIES_ENABLED", False)
    monkeypatch.setattr(instagram_cookies, "INSTAGRAM_COOKIES", None)

    assert instagram_cookies.build_instagram_cookie_opts() == {}


def test_instagram_cookie_opts_valid_file(monkeypatch, tmp_path: Path) -> None:
    """При валидном cookie-файле должен возвращаться путь к runtime-копии."""
    cookie_file = tmp_path / "instagram_cookies.txt"
    cookie_file.write_text(
        "# Netscape HTTP Cookie File\n"
        ".instagram.com\tTRUE\t/\tTRUE\t2147483647\tsessionid\ttest-session\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(instagram_cookies, "INSTAGRAM_COOKIES_ENABLED", True)
    monkeypatch.setattr(instagram_cookies, "INSTAGRAM_COOKIES", cookie_file)

    opts = instagram_cookies.build_instagram_cookie_opts()
    assert "cookiefile" in opts

    runtime_cookiefile = Path(str(opts["cookiefile"]))
    assert runtime_cookiefile.exists()
    assert runtime_cookiefile != cookie_file
    assert runtime_cookiefile.read_text(encoding="utf-8") == cookie_file.read_text(encoding="utf-8")


def test_instagram_cookie_opts_placeholder(monkeypatch, tmp_path: Path) -> None:
    """Пустой/заглушечный cookie-файл должен игнорироваться."""
    cookie_file = tmp_path / "instagram_cookies.txt"
    cookie_file.write_text("", encoding="utf-8")

    monkeypatch.setattr(instagram_cookies, "INSTAGRAM_COOKIES_ENABLED", True)
    monkeypatch.setattr(instagram_cookies, "INSTAGRAM_COOKIES", cookie_file)

    assert instagram_cookies.build_instagram_cookie_opts() == {}
