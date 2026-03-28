"""Unit-tests for VK URL normalization and handler matching."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# test/handlers/VK/test_vk_url_service.py -> project root это parents[3]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Минимальные env для загрузки src.config.
os.environ.setdefault("BOT_DB_PATH", str(PROJECT_ROOT / "src" / "data" / "db" / "bot.db"))
os.environ.setdefault("BOT_VERSION", "local-test")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("BOT_TOKEN", "local-test-token")
os.environ.setdefault("YANDEX_MUSIC_TOKEN", "local-test-token")

from src.handlers.resources.VK.VKHandler import VKHandler
from src.handlers.resources.VK.VKUrlService import VKUrlService


def test_vk_url_service_normalize_unifies_hosts_and_strips_tracking_query() -> None:
    """VK URL normalizer should collapse supported hosts and drop tracking params."""
    service = VKUrlService()

    normalized = service.normalize("https://vkvideo.ru/clip-1_2?from=feed&w=wall-1_2&list=custom")

    assert normalized == "https://vk.com/clip-1_2?list=custom"


def test_vk_url_service_rejects_reserved_paths_from_profile_classification() -> None:
    """Reserved VK paths should not be classified as profile/community URLs."""
    service = VKUrlService()

    content_type, content_match = service.detect_content_type("https://vk.com/login")

    assert content_type is None
    assert content_match is None


def test_vk_handler_pattern_skips_reserved_vk_slugs() -> None:
    """Handler-level pattern should stay aligned with reserved VK URL filtering."""
    assert VKHandler.PATTERN.match("https://vk.com/spaces")
    assert not VKHandler.PATTERN.match("https://vk.com/login")
    assert not VKHandler.PATTERN.match("https://vk.com/badbrowser.php")
