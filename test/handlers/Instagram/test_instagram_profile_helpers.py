"""Unit-тесты helper-логики InstagramProfile."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# test/handlers/Instagram/test_instagram_profile_helpers.py -> project root это parents[3]
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

from src.handlers.resources.Instagram.InstagramHandler import InstagramHandler


def test_extract_username_from_profile_url_with_query() -> None:
    """
    Username должен корректно извлекаться из profile URL с query-параметрами.
    """
    handler = InstagramHandler()
    url = "https://www.instagram.com/photo_by_malyshev?igsh=aGg5bHU3eTNjZ2Zk"

    assert handler._extract_username_from_url(url) == "photo_by_malyshev"


def test_build_canonical_profile_url() -> None:
    """
    Канонический URL профиля всегда завершается на `/`.
    """
    handler = InstagramHandler()
    assert (
        handler._build_canonical_profile_url("photo_by_malyshev")
        == "https://www.instagram.com/photo_by_malyshev/"
    )


def test_build_metadata_from_web_profile_user() -> None:
    """
    Payload web_profile_info должен корректно маппиться в формат metadata.
    """
    handler = InstagramHandler()
    payload = {
        "full_name": "Photo By Malyshev",
        "biography": "Test bio",
        "profile_pic_url_hd": "https://example.com/avatar.jpg",
        "edge_followed_by": {"count": 12345},
        "edge_owner_to_timeline_media": {"count": 678},
    }

    metadata = handler._build_metadata_from_web_profile_user(
        user_payload=payload,
        username="photo_by_malyshev",
    )

    assert metadata["uploader_id"] == "photo_by_malyshev"
    assert metadata["channel"] == "Photo By Malyshev"
    assert metadata["description"] == "Test bio"
    assert metadata["channel_follower_count"] == 12345
    assert metadata["media_count"] == 678
    assert metadata["thumbnail"] == "https://example.com/avatar.jpg"
    assert metadata["webpage_url"] == "https://www.instagram.com/photo_by_malyshev/"

