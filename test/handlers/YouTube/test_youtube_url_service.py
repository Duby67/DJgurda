"""Unit-тесты для `YouTubeUrlService`."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# test/handlers/YouTube/test_youtube_url_service.py -> project root это parents[3]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
HANDLERS_TEST_ROOT = PROJECT_ROOT / "test" / "handlers"
if str(HANDLERS_TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(HANDLERS_TEST_ROOT))

# Минимальные env для загрузки src.config.
os.environ.setdefault("BOT_DB_PATH", str(PROJECT_ROOT / "src" / "data" / "db" / "bot.db"))
os.environ.setdefault("BOT_VERSION", "local-test")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("BOT_TOKEN", "local-test-token")
os.environ.setdefault("YANDEX_MUSIC_TOKEN", "local-test-token")
os.environ.setdefault("YOUTUBE_COOKIES_ENABLED", "false")

from src.handlers.resources.YouTube.YouTubeUrlService import YouTubeUrlService
from YouTube_urls import (
    YOUTUBE_URL_SERVICE_CLASSIFICATION_CASES,
    YOUTUBE_URL_SERVICE_NORMALIZATION_CASES,
)


def _build_service() -> YouTubeUrlService:
    """Создает сервис URL-классификации."""
    return YouTubeUrlService()


@pytest.mark.parametrize("case", YOUTUBE_URL_SERVICE_NORMALIZATION_CASES, ids=lambda case: case["name"])
def test_normalize_removes_tracking_params_and_canonicalizes_host(case: dict[str, str]) -> None:
    """Нормализация должна убирать tracking-параметры и приводить host к каноническому виду."""
    service = _build_service()

    assert service.normalize(case["url"]) == case["normalized_url"]


@pytest.mark.parametrize("case", YOUTUBE_URL_SERVICE_CLASSIFICATION_CASES, ids=lambda case: case["name"])
def test_detect_content_type_matches_url_shape(case: dict[str, str]) -> None:
    """Классификация должна покрывать поддерживаемые YouTube URL-формы."""
    service = _build_service()

    assert service.detect_content_type(case["url"]) == case["expected_type"]
