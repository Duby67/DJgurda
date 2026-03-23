"""Регресс-тесты выбора target URL внутри `YouTubeHandler`."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# test/handlers/YouTube/test_youtube_handler_routing.py -> project root это parents[3]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("BOT_DB_PATH", str(PROJECT_ROOT / "src" / "data" / "db" / "bot.db"))
os.environ.setdefault("BOT_VERSION", "local-test")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("BOT_TOKEN", "local-test-token")
os.environ.setdefault("YANDEX_MUSIC_TOKEN", "local-test-token")
os.environ.setdefault("YOUTUBE_COOKIES_ENABLED", "false")

from src.handlers.resources.YouTube.YouTubeHandler import YouTubeHandler


def test_pick_target_url_keeps_original_shorts_when_resolved_becomes_watch() -> None:
    """Shorts intent не должен теряться, если resolved URL деградирует до watch."""
    handler = YouTubeHandler()

    target_url, content_type = handler._pick_target_url(
        original_url="https://www.youtube.com/shorts/OUBWpfoBd9M",
        resolved_url="https://www.youtube.com/watch?v=OUBWpfoBd9M",
    )

    assert target_url == "https://www.youtube.com/shorts/OUBWpfoBd9M"
    assert content_type == "shorts"
