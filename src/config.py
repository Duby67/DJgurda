"""Конфигурация приложения, загружаемая из переменных окружения."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Ограничения Telegram и медиа-контента.
MAX_CAPTION = 1024
MAX_AGE_SECONDS = 3600
PHOTO_SIZE_LIMIT = 10 * 1024 * 1024
VIDEO_SIZE_LIMIT = 50 * 1024 * 1024
AUDIO_SIZE_LIMIT = 50 * 1024 * 1024

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROJECT_TEMP_DIR = PROJECT_ROOT / "src" / "data" / "temp_files"


def _require_env(name: str) -> str:
    """Возвращает обязательное значение env или выбрасывает понятную ошибку."""
    value = os.getenv(name)
    if not value:
        raise ValueError(f"{name} не найден в .env!")
    return value


def _require_int_env(name: str) -> int:
    """Возвращает обязательное целочисленное значение env или выбрасывает ошибку."""
    value = _require_env(name)
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} должен быть числом") from exc


DB_PATH = _require_env("BOT_DB_PATH")
BOT_VERSION = _require_env("BOT_VERSION")
ADMIN_ID = _require_int_env("ADMIN_ID")
BOT_TOKEN = _require_env("BOT_TOKEN")
YANDEX_MUSIC_TOKEN = _require_env("YANDEX_MUSIC_TOKEN")

YOUTUBE_COOKIES_PATH = _require_env("YOUTUBE_COOKIES_PATH")
YOUTUBE_COOKIES = Path(YOUTUBE_COOKIES_PATH).resolve()
if not YOUTUBE_COOKIES.exists():
    raise ValueError("Файл YOUTUBE_COOKIES не найден.")
