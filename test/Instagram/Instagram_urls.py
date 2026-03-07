"""Совместимый импорт тестовых URL Instagram из файла `source_urls.py`."""

from source_urls import (
    INSTAGRAM_TEST_CASES,
    MEDIA_GROUP_URL,
    PROFILE_URL,
    REELS_URL,
    STORIES_URL,
)

__all__ = [
    "PROFILE_URL",
    "REELS_URL",
    "MEDIA_GROUP_URL",
    "STORIES_URL",
    "INSTAGRAM_TEST_CASES",
]
