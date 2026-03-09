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


def _resolve_path(path_value: str, *, base_dir: Path = PROJECT_ROOT) -> Path:
    """Нормализует путь (с поддержкой `~`) и возвращает абсолютный Path."""
    expanded = Path(os.path.expandvars(path_value)).expanduser()
    if not expanded.is_absolute():
        expanded = base_dir / expanded
    return expanded.resolve()


DB_PATH = _require_env("BOT_DB_PATH")
DB_FILE = _resolve_path(DB_PATH)
BOT_VERSION = _require_env("BOT_VERSION")
ADMIN_ID = _require_int_env("ADMIN_ID")
BOT_TOKEN = _require_env("BOT_TOKEN")
YANDEX_MUSIC_TOKEN = _require_env("YANDEX_MUSIC_TOKEN")

BOT_TEMP_DIR_PATH = os.getenv("BOT_TEMP_DIR", "").strip()
DEFAULT_TEMP_DIR = (PROJECT_ROOT / "src" / "data" / "temp_files").resolve()
PROJECT_TEMP_DIR = _resolve_path(BOT_TEMP_DIR_PATH) if BOT_TEMP_DIR_PATH else DEFAULT_TEMP_DIR

DEFAULT_COOKIES_DIR = PROJECT_ROOT / "src" / "data" / "cookies"
COOKIES_DIR_PATH = os.getenv("COOKIES_DIR", "").strip()
COOKIES_DIR = _resolve_path(COOKIES_DIR_PATH) if COOKIES_DIR_PATH else DEFAULT_COOKIES_DIR


def _resolve_cookie_path(env_name: str, fallback_filename: str) -> tuple[str, Path]:
    """
    Возвращает итоговый путь cookies-файла:
    - явный `*_COOKIES_PATH`, если задан;
    - иначе `<COOKIES_DIR>/<fallback_filename>`.
    """
    explicit_path = os.getenv(env_name, "").strip()
    if explicit_path:
        return explicit_path, _resolve_path(explicit_path)

    fallback_path = (COOKIES_DIR / fallback_filename).resolve()
    return str(fallback_path), fallback_path


YOUTUBE_COOKIES_ENABLED = _read_bool_env("YOUTUBE_COOKIES_ENABLED", default=True)
YOUTUBE_COOKIES_PATH, YOUTUBE_COOKIES = _resolve_cookie_path(
    env_name="YOUTUBE_COOKIES_PATH",
    fallback_filename="www.youtube.com_cookies.txt",
)

INSTAGRAM_COOKIES_ENABLED = _read_bool_env("INSTAGRAM_COOKIES_ENABLED", default=True)
INSTAGRAM_COOKIES_PATH, INSTAGRAM_COOKIES = _resolve_cookie_path(
    env_name="INSTAGRAM_COOKIES_PATH",
    fallback_filename="instagram_cookies.txt",
)

TIKTOK_COOKIES_ENABLED = _read_bool_env("TIKTOK_COOKIES_ENABLED", default=True)
TIKTOK_COOKIES_PATH, TIKTOK_COOKIES = _resolve_cookie_path(
    env_name="TIKTOK_COOKIES_PATH",
    fallback_filename="tiktok_cookies.txt",
)

VK_COOKIES_ENABLED = _read_bool_env("VK_COOKIES_ENABLED", default=True)
VK_COOKIES_PATH, VK_COOKIES = _resolve_cookie_path(
    env_name="VK_COOKIES_PATH",
    fallback_filename="vk.com_cookies.txt",
)
