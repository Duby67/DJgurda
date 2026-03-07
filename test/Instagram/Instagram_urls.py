"""Набор URL-заглушек для локальной проверки InstagramHandler.

Файл подготовлен как заготовка для будущего smoke-теста, когда будет
добавлен отдельный тестовый скрипт для Instagram.
"""

from __future__ import annotations

from typing import Final

# Кейс: профиль Instagram (заглушка).
PROFILE_URL: Final[str] = "https://www.instagram.com/profile_placeholder/"

# Кейс: Reels-публикация Instagram (заглушка).
REELS_URL: Final[str] = "https://www.instagram.com/reel/REELS_PLACEHOLDER/"

# Кейс: медиагруппа (carousel) Instagram (заглушка).
MEDIA_GROUP_URL: Final[str] = "https://www.instagram.com/p/MEDIA_GROUP_PLACEHOLDER/"

# Кейс: Stories-ссылка Instagram (заглушка).
STORIES_URL: Final[str] = "https://www.instagram.com/stories/stories_placeholder/1234567890123456789/"

INSTAGRAM_TEST_CASES: Final[tuple[dict[str, str], ...]] = (
    {
        "name": "profile",
        "url": PROFILE_URL,
        "description": "Профиль Instagram (URL-заглушка).",
    },
    {
        "name": "reels",
        "url": REELS_URL,
        "description": "Короткое видео Reels (URL-заглушка).",
    },
    {
        "name": "media_group",
        "url": MEDIA_GROUP_URL,
        "description": "Пост-карусель с несколькими медиа (URL-заглушка).",
    },
    {
        "name": "stories",
        "url": STORIES_URL,
        "description": "Ссылка на stories-контент (URL-заглушка).",
    },
)

