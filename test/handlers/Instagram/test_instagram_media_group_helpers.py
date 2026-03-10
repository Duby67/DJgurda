"""Unit-тесты helper-логики Instagram media_group."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# test/handlers/Instagram/test_instagram_media_group_helpers.py -> project root это parents[3]
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

from src.handlers.resources.Instagram.InstagramMediaGroup import InstagramMediaGroup


def test_normalize_media_group_url_drops_img_index() -> None:
    """
    Параметр img_index должен удаляться, чтобы обработка шла по всей карусели.
    """
    url = "https://www.instagram.com/p/DVk2sEcDPwp/?img_index=1&foo=bar"

    normalized = InstagramMediaGroup.normalize_media_group_url(url)
    assert normalized == "https://www.instagram.com/p/DVk2sEcDPwp/?foo=bar"


def test_normalize_media_group_url_keeps_non_img_index_params() -> None:
    """
    Нецелевые query-параметры должны сохраняться.
    """
    url = "https://www.instagram.com/p/DVk2sEcDPwp/?foo=bar&baz=1"

    normalized = InstagramMediaGroup.normalize_media_group_url(url)
    assert normalized == "https://www.instagram.com/p/DVk2sEcDPwp/?foo=bar&baz=1"