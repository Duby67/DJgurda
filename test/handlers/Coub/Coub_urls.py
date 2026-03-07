"""Набор тестовых URL для локального smoke-теста CoubHandler.

Файл служит единым источником правды для тестовых ссылок:
- сюда добавляются/обновляются кейсы для проверки обработчика;
- скрипт `test_coub_handlers_local.py` читает ссылки только из этого файла.
"""

from __future__ import annotations

from typing import Final

# Кейс: стандартная ссылка COUB формата /view/<id>.
# Ожидаем, что обработчик вернет type='video'.
VIDEO_VIEW_URL: Final[str] = "https://coub.com/view/480igm"

COUB_TEST_CASES: Final[tuple[dict[str, str], ...]] = (
    {
        "name": "video_view",
        "url": VIDEO_VIEW_URL,
        "expected_type": "video",
        "description": "COUB-видео формата /view/<id>.",
    },
)
