"""Набор тестовых URL для локального smoke-теста YouTubeHandler.

Файл служит единым источником правды для тестовых ссылок:
- сюда добавляются/обновляются кейсы для проверки обработчика;
- скрипт `test_youtube_handlers_local.py` читает ссылки только из этого файла.
"""

from __future__ import annotations

from typing import Final

# Кейс: YouTube Shorts.
# Ожидаем, что обработчик вернет type='shorts'.
SHORTS_URL: Final[str] = "https://www.youtube.com/shorts/FTKTL9-hcGw"

# Кейс: профиль канала YouTube (handle-страница).
# Ожидаем, что обработчик вернет type='channel'.
CHANNEL_PROFILE_URL: Final[str] = "https://www.youtube.com/@IDIM20247"

YOUTUBE_TEST_CASES: Final[tuple[dict[str, str], ...]] = (
    {
        "name": "shorts",
        "url": SHORTS_URL,
        "expected_type": "shorts",
        "description": "Короткое вертикальное видео YouTube Shorts.",
    },
    {
        "name": "channel_profile",
        "url": CHANNEL_PROFILE_URL,
        "expected_type": "channel",
        "description": "Профиль/страница канала YouTube (@handle).",
    },
)

