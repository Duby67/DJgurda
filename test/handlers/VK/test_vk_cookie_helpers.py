"""Unit-tests for VK cookie and browser-header helpers."""

from __future__ import annotations

import os
import sys
from pathlib import Path
import logging

# test/handlers/VK/test_vk_cookie_helpers.py -> project root это parents[3]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Минимальные env для загрузки src.config.
os.environ.setdefault("BOT_DB_PATH", str(PROJECT_ROOT / "src" / "data" / "db" / "bot.db"))
os.environ.setdefault("BOT_VERSION", "local-test")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("BOT_TOKEN", "local-test-token")
os.environ.setdefault("YANDEX_MUSIC_TOKEN", "local-test-token")

from src.handlers.resources.VK.VKDependencies import VKRequestContext
from src.utils.cookies import CookieFile


def test_vk_user_id_falls_back_to_remixstid_prefix_when_remixuserid_is_missing() -> None:
    """VK audio decode should still recover user id from remixstid-only cookies."""
    cookies = {
        "remixsid": "session-token",
        "remixstid": "146383805_a1b2c3d4e5f6",
    }

    assert VKRequestContext._extract_vk_user_id_from_cookies(cookies) == 146383805


def test_vk_user_id_prefers_explicit_remixuserid_when_it_is_available() -> None:
    """Explicit remixuserid should win over fallback parsing from remixstid."""
    cookies = {
        "remixuserid": "157641179",
        "remixstid": "146383805_a1b2c3d4e5f6",
    }

    assert VKRequestContext._extract_vk_user_id_from_cookies(cookies) == 157641179


def test_vk_domain_cookie_buckets_keep_vk_and_vkvideo_values_separate(tmp_path: Path) -> None:
    """Merged cookie files should preserve host-specific values for aiohttp requests."""
    cookie_file = tmp_path / "vk_merged_cookies.txt"
    cookie_file.write_text(
        "# Netscape HTTP Cookie File\n"
        ".vk.com\tTRUE\t/\tTRUE\t2147483647\tremixstid\t111_vkcom\n"
        ".vk.com\tTRUE\t/\tTRUE\t2147483647\thttoken\tvkcom-token\n"
        ".vkvideo.ru\tTRUE\t/\tTRUE\t2147483647\tremixstid\t222_vkvideo\n"
        ".vkvideo.ru\tTRUE\t/\tTRUE\t2147483647\thttoken\tvkvideo-token\n",
        encoding="utf-8",
    )

    buckets = VKRequestContext._load_domain_cookie_buckets(cookie_file)
    assert buckets["vk.com"]["remixstid"] == "111_vkcom"
    assert buckets["vkvideo.ru"]["remixstid"] == "222_vkvideo"

    ctx = VKRequestContext.__new__(VKRequestContext)
    ctx._vk_cookies = CookieFile(
        provider_key="vk",
        provider_name="VK",
        enabled=True,
        cookie_path=cookie_file,
        path_env_name="VK_COOKIES_PATH",
        runtime_dir=tmp_path,
        log=logging.getLogger(__name__),
    )
    ctx._cookie_buckets = buckets
    ctx._request_cookies = ctx._build_default_request_cookies()

    assert ctx._cookies_for_url("https://vk.com/audio123_456")["httoken"] == "vkcom-token"
    assert ctx._cookies_for_url("https://vkvideo.ru/clip-1_2")["httoken"] == "vkvideo-token"
