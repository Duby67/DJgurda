"""Набор тестовых URL для локального smoke-теста VKHandler.

Файл служит единым источником правды для тестовых ссылок:
- сюда добавляются/обновляются кейсы для проверки обработчика;
- скрипт `test_vk_handlers_local.py` читает ссылки только из этого файла.
"""

from __future__ import annotations

from typing import Final

# Кейс: плейлист VK Music.
# Ожидаем, что обработчик вернет type='playlist' и список треков в metadata.
PLAYLIST_URL: Final[str] = "https://vk.com/music/playlist/157641179_82666564_abb72520100a48b9e1"

# Кейсы: одиночные треки VK Music.
# Ожидаем, что обработчик вернет type='audio' и скачает аудиофайл.
TRACK_URL_1: Final[str] = "https://vk.ru/audio157641179_456242198_61f1ff87b55571147c"
TRACK_URL_2: Final[str] = "https://vk.ru/audio157641179_456242192_afe4104bbc1c949acd"
TRACK_URL_3: Final[str] = "https://vk.ru/audio157641179_456242185_9df0c157a56a30f1bc"

VK_PLAYLIST_TEST_CASE: Final[dict[str, str]] = {
    "name": "playlist",
    "url": PLAYLIST_URL,
    "expected_type": "playlist",
    "description": "VK Music playlist URL (парсинг playlist metadata без массовой загрузки файлов).",
}

VK_TRACK_TEST_CASES: Final[tuple[dict[str, str], ...]] = (
    {
        "name": "track_1",
        "url": TRACK_URL_1,
        "expected_type": "audio",
        "description": "Одиночный трек VK Music (кейс 1).",
    },
    {
        "name": "track_2",
        "url": TRACK_URL_2,
        "expected_type": "audio",
        "description": "Одиночный трек VK Music (кейс 2).",
    },
    {
        "name": "track_3",
        "url": TRACK_URL_3,
        "expected_type": "audio",
        "description": "Одиночный трек VK Music (кейс 3).",
    },
)
