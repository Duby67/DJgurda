"""Набор тестовых URL для локального smoke-теста YandexMusicHandler.

Файл служит единым источником правды для тестовых ссылок:
- сюда добавляются/обновляются кейсы для проверки обработчика;
- скрипт `test_yandex_music_handlers_local.py` читает ссылки только из этого файла.
"""

from __future__ import annotations

from typing import Final

# Кейс: трек Yandex Music (пользовательская ссылка #1).
# Ожидаем, что обработчик вернет type='audio'.
TRACK_URL_1: Final[str] = (
    "https://music.yandex.ru/album/35060736/track/135369533?utm_source=desktop&utm_medium=copy_link"
)

# Кейс: трек Yandex Music (пользовательская ссылка #2).
# Ожидаем, что обработчик вернет type='audio'.
TRACK_URL_2: Final[str] = (
    "https://music.yandex.ru/album/36516641/track/138903917?utm_source=desktop&utm_medium=copy_link"
)

# Кейс: трек Yandex Music (пользовательская ссылка #3).
# Ожидаем, что обработчик вернет type='audio'.
TRACK_URL_3: Final[str] = (
    "https://music.yandex.ru/album/40341803/track/147488879?utm_source=desktop&utm_medium=copy_link"
)

YANDEX_MUSIC_TEST_CASES: Final[tuple[dict[str, str], ...]] = (
    {
        "name": "track_135369533",
        "url": TRACK_URL_1,
        "expected_type": "audio",
        "description": "Трек Yandex Music: album/35060736 track/135369533.",
    },
    {
        "name": "track_138903917",
        "url": TRACK_URL_2,
        "expected_type": "audio",
        "description": "Трек Yandex Music: album/36516641 track/138903917.",
    },
    {
        "name": "track_147488879",
        "url": TRACK_URL_3,
        "expected_type": "audio",
        "description": "Трек Yandex Music: album/40341803 track/147488879.",
    },
)
