"""Unit-tests for VK cookie and browser-header helpers."""

from __future__ import annotations

import os
import sys
from pathlib import Path

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
