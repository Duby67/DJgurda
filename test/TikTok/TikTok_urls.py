"""Набор тестовых URL для локального smoke-теста TikTokHandler.

Файл служит единым источником правды для тестовых ссылок:
- сюда добавляются/обновляются кейсы для проверки обработчика;
- скрипт `test_tiktok_handlers_local.py` читает ссылки только из этого файла.
"""

from __future__ import annotations

from typing import Final

# Кейс: короткая ссылка на обычный TikTok-видеопост.
# Ожидаем, что обработчик вернет type='video'.
VIDEO_URL: Final[str] = "https://www.tiktok.com/t/ZP8Qt8vYy/"

# Кейс: ссылка на профиль автора.
# Ожидаем, что обработчик вернет type='profile'.
PROFILE_URL: Final[str] = "https://www.tiktok.com/@zookeeper067?_r=1&_t=ZP-94R0oHXRRjr"

# Кейс: короткая ссылка на photo/slideshow-пост (media_group).
# Ожидаем, что обработчик вернет type='media_group'
# и сможет собрать фото + фоновую музыку.
MEDIA_GROUP_URL: Final[str] = "https://www.tiktok.com/t/ZP8QGw9rA/"

TIKTOK_TEST_CASES: Final[tuple[dict[str, str], ...]] = (
    {
        "name": "video",
        "url": VIDEO_URL,
        "expected_type": "video",
        "description": "Обычный видеопост TikTok через короткую ссылку tiktok.com/t/...",
    },
    {
        "name": "profile",
        "url": PROFILE_URL,
        "expected_type": "profile",
        "description": "Профиль автора TikTok (парсинг профиля и аватара).",
    },
    {
        "name": "media_group",
        "url": MEDIA_GROUP_URL,
        "expected_type": "media_group",
        "description": "Фото/слайдшоу-пост TikTok с фоновой музыкой.",
    },
)

