"""Набор тестовых URL для локальной проверки YouTubeHandler.

Файл используется как единый источник тестовых ссылок YouTube для ручных
и будущих smoke-проверок обработчика.
"""

from __future__ import annotations

from typing import Final

# Кейс: профиль (страница канала) YouTube.
# Используется для проверки сценария обработки ссылок на канал.
CHANNEL_PROFILE_URL: Final[str] = "https://www.youtube.com/@IDIM20247"

# Кейс: YouTube Shorts.
# Используется для проверки обработки короткого вертикального видео.
SHORTS_URL: Final[str] = "https://www.youtube.com/shorts/FTKTL9-hcGw"

YOUTUBE_TEST_CASES: Final[tuple[dict[str, str], ...]] = (
    {
        "name": "channel_profile",
        "url": CHANNEL_PROFILE_URL,
        "description": "Профиль канала YouTube (@handle).",
    },
    {
        "name": "shorts",
        "url": SHORTS_URL,
        "description": "Короткое видео в формате YouTube Shorts.",
    },
)

