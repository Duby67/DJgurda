"""Unit-тесты helper-логики Instagram cookies."""

from __future__ import annotations

import logging
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

from src.utils.cookies import build_ytdlp_cookiefile_opt

_TEST_LOGGER = logging.getLogger(__name__)


def test_instagram_cookie_opts_disabled() -> None:
    """При отключенном флаге cookies не должны передаваться."""
    assert (
        build_ytdlp_cookiefile_opt(
            provider_key="instagram",
            provider_name="Instagram",
            enabled=False,
            cookie_path=None,
            path_env_name="INSTAGRAM_COOKIES_PATH",
            log=_TEST_LOGGER,
        )
        == {}
    )


def test_instagram_cookie_opts_valid_file(tmp_path: Path) -> None:
    """При валидном cookie-файле должен возвращаться путь к временной копии."""
    cookie_file = tmp_path / "instagram_cookies.txt"
    cookie_file.write_text(
        "# Netscape HTTP Cookie File\n"
        ".instagram.com\tTRUE\t/\tTRUE\t2147483647\tsessionid\ttest-session\n",
        encoding="utf-8",
    )

    opts = build_ytdlp_cookiefile_opt(
        provider_key="instagram",
        provider_name="Instagram",
        enabled=True,
        cookie_path=cookie_file,
        path_env_name="INSTAGRAM_COOKIES_PATH",
        log=_TEST_LOGGER,
    )
    assert "cookiefile" in opts

    temp_cookiefile = Path(str(opts["cookiefile"]))
    assert temp_cookiefile.exists()
    assert temp_cookiefile != cookie_file
    assert temp_cookiefile.read_text(encoding="utf-8") == cookie_file.read_text(encoding="utf-8")


def test_instagram_cookie_opts_placeholder(tmp_path: Path) -> None:
    """Пустой/заглушечный cookie-файл должен игнорироваться."""
    cookie_file = tmp_path / "instagram_cookies.txt"
    cookie_file.write_text("", encoding="utf-8")

    assert (
        build_ytdlp_cookiefile_opt(
            provider_key="instagram",
            provider_name="Instagram",
            enabled=True,
            cookie_path=cookie_file,
            path_env_name="INSTAGRAM_COOKIES_PATH",
            log=_TEST_LOGGER,
        )
        == {}
    )
