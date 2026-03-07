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
STATISTICS_TOP_USERS_LIMIT = 3

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


def _read_bool_env(name: str, default: bool = False) -> bool:
    """Читает bool-переменную окружения в формате true/false, 1/0, yes/no, on/off."""
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False

    raise ValueError(f"{name} должен быть bool-значением (true/false, 1/0, yes/no, on/off)")


DB_PATH = _require_env("BOT_DB_PATH")
BOT_VERSION = _require_env("BOT_VERSION")
ADMIN_ID = _require_int_env("ADMIN_ID")
BOT_TOKEN = _require_env("BOT_TOKEN")
YANDEX_MUSIC_TOKEN = _require_env("YANDEX_MUSIC_TOKEN")

YOUTUBE_COOKIES_ENABLED = _read_bool_env("YOUTUBE_COOKIES_ENABLED", default=False)
YOUTUBE_COOKIES_PATH = os.getenv("YOUTUBE_COOKIES_PATH", "").strip()
YOUTUBE_COOKIES = Path(YOUTUBE_COOKIES_PATH).resolve() if YOUTUBE_COOKIES_PATH else None

if YOUTUBE_COOKIES_ENABLED:
    if not YOUTUBE_COOKIES_PATH:
        raise ValueError("YOUTUBE_COOKIES_ENABLED=true требует заданный YOUTUBE_COOKIES_PATH.")
    if YOUTUBE_COOKIES is None or not YOUTUBE_COOKIES.exists():
        raise ValueError("Файл YOUTUBE_COOKIES не найден.")
