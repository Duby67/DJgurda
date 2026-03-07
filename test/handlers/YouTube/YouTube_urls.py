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

# Кейс: interstitial-ссылка согласия YouTube, которая должна
# распаковаться обратно в shorts URL.
CONSENT_SHORTS_URL: Final[str] = (
    "https://consent.youtube.com/ml?"
    "continue=https%3A%2F%2Fwww.youtube.com%2Fshorts%2FFTKTL9-hcGw%3Fcbrd%3D1"
    "&gl=NL&hl=nl&cm=2&pc=yt&src=1"
)

# Кейс: interstitial-ссылка согласия YouTube с относительным continue.
# Ожидаем распаковку в абсолютный shorts URL.
CONSENT_SHORTS_RELATIVE_URL: Final[str] = (
    "https://consent.youtube.com/ml?"
    "continue=%2Fshorts%2FFTKTL9-hcGw%3Fcbrd%3D1"
    "&gl=NL&hl=nl&cm=2&pc=yt&src=1"
)

YOUTUBE_TEST_CASES: Final[tuple[dict[str, str], ...]] = (
    {
        "name": "shorts",
        "url": SHORTS_URL,
        "expected_type": "shorts",
        "description": "Короткое вертикальное видео YouTube Shorts.",
    },
    {
        "name": "shorts_consent",
        "url": CONSENT_SHORTS_URL,
        "expected_type": "shorts",
        "description": "YouTube consent-ссылка должна распаковываться до shorts.",
    },
    {
        "name": "shorts_consent_relative",
        "url": CONSENT_SHORTS_RELATIVE_URL,
        "expected_type": "shorts",
        "description": "YouTube consent-ссылка с относительным continue.",
    },
    {
        "name": "channel_profile",
        "url": CHANNEL_PROFILE_URL,
        "expected_type": "channel",
        "description": "Профиль/страница канала YouTube (@handle).",
    },
)
