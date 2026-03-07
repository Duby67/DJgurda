"""Регресс-тест выбора счетчика видео для YouTube channel."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# test/handlers/YouTube/test_youtube_channel_video_count.py -> project root это parents[3]
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

from src.handlers.resources.YouTube.YouTubeHandler import YouTubeHandler


def test_channel_video_count_has_priority_over_playlist_count() -> None:
    """
    Для карточки канала приоритетом должно быть общее число видео,
    а не количество плейлистов.
    """
    handler = YouTubeHandler()
    info = {
        "playlist_count": 2,
        "channel_video_count": 75,
    }

    assert handler._extract_total_videos_count(info) == "75"


def test_playlist_count_is_used_as_fallback() -> None:
    """
    Если общего числа видео нет, разрешается использовать playlist_count как fallback.
    """
    handler = YouTubeHandler()
    info = {"playlist_count": 2}

    assert handler._extract_total_videos_count(info) == "2"


def test_build_videos_tab_url_from_channel_id() -> None:
    """
    Для channel-id URL должен строиться путь на вкладку videos.
    """
    handler = YouTubeHandler()
    url = "https://www.youtube.com/channel/UCALIGDpGpOmezPu0xujHzqA"

    assert handler._build_videos_tab_url(url) == "https://www.youtube.com/channel/UCALIGDpGpOmezPu0xujHzqA/videos"


def test_build_videos_tab_url_from_handle_root() -> None:
    """
    Для handle-страницы должен добавляться суффикс /videos.
    """
    handler = YouTubeHandler()
    url = "https://www.youtube.com/@IDIM20247"

    assert handler._build_videos_tab_url(url) == "https://www.youtube.com/@IDIM20247/videos"


def test_build_videos_tab_url_replaces_other_tab() -> None:
    """
    Для вкладок типа /about должен подставляться /videos.
    """
    handler = YouTubeHandler()
    url = "https://www.youtube.com/@IDIM20247/about"

    assert handler._build_videos_tab_url(url) == "https://www.youtube.com/@IDIM20247/videos"
