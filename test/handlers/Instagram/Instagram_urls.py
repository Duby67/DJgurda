"""Набор тестовых URL для локального smoke-теста InstagramHandler.

Файл служит единым источником правды для тестовых ссылок:
- сюда добавляются/обновляются кейсы для проверки обработчика;
- скрипт `test_instagram_handlers_local.py` читает ссылки только из этого файла.
"""

from __future__ import annotations

from typing import Final

# Кейс: профиль Instagram.
# Ожидаем, что обработчик вернет type='profile'.
PROFILE_URL: Final[str] = "https://www.instagram.com/instagram/"

# Кейс: Reels-публикация Instagram.
# Ожидаем, что обработчик вернет type='reels'.
REELS_URL: Final[str] = "https://www.instagram.com/reel/C2s3v86L3sM/"

# Кейс: carousel-пост Instagram.
# Ожидаем, что обработчик вернет type='media_group'.
MEDIA_GROUP_URL: Final[str] = "https://www.instagram.com/p/DVk2sEcDPwp/?img_index=1&igsh=MTlwMWg5cXZ3cWt0bg=="

# Кейс: Stories-ссылка Instagram.
# Ожидаем, что обработчик вернет type='stories'.
STORIES_URL: Final[str] = "https://www.instagram.com/stories/elvirasharma/3847664882045214989?utm_source=ig_story_item_share&igsh=MXN6Ynp0NGNlaDhkbA=="

# Кейс: interstitial-ссылка l.instagram.com с параметром `u`.
# Ожидаем, что resolve_url распакует ее до profile URL.
WRAPPED_PROFILE_URL: Final[str] = (
    "https://l.instagram.com/?"
    "u=https%3A%2F%2Fwww.instagram.com%2Finstagram%2F"
    "&e=AT0"
)

# Кейс: interstitial-ссылка l.instagram.com с относительным `u`.
# Ожидаем распаковку в абсолютный profile URL.
WRAPPED_PROFILE_RELATIVE_URL: Final[str] = (
    "https://l.instagram.com/?"
    "u=%2Finstagram%2F"
    "&e=AT0"
)

INSTAGRAM_TEST_CASES: Final[tuple[dict[str, str], ...]] = (
    {
        "name": "profile",
        "url": PROFILE_URL,
        "expected_type": "profile",
        "description": "Профиль Instagram (@username).",
    },
    {
        "name": "profile_wrapped",
        "url": WRAPPED_PROFILE_URL,
        "expected_type": "profile",
        "description": "Interstitial l.instagram.com должен распаковываться в профиль.",
    },
    {
        "name": "profile_wrapped_relative",
        "url": WRAPPED_PROFILE_RELATIVE_URL,
        "expected_type": "profile",
        "description": "Interstitial l.instagram.com с относительным u.",
    },
    {
        "name": "reels",
        "url": REELS_URL,
        "expected_type": "reels",
        "description": "Видео в формате Instagram Reels.",
    },
    {
        "name": "media_group",
        "url": MEDIA_GROUP_URL,
        "expected_type": "media_group",
        "description": "Пост-карусель Instagram (несколько медиа).",
    },
    {
        "name": "stories",
        "url": STORIES_URL,
        "expected_type": "stories",
        "description": "Ссылка на Instagram Stories.",
    },
)
