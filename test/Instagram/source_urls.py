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
MEDIA_GROUP_URL: Final[str] = "https://www.instagram.com/p/C2s3R9DrQjL/"

# Кейс: Stories-ссылка Instagram.
# Ожидаем, что обработчик вернет type='stories'.
STORIES_URL: Final[str] = "https://www.instagram.com/stories/instagram/3283285557542675306/"

INSTAGRAM_TEST_CASES: Final[tuple[dict[str, str], ...]] = (
    {
        "name": "profile",
        "url": PROFILE_URL,
        "expected_type": "profile",
        "description": "Профиль Instagram (@username).",
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

