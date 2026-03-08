"""
Утилиты для безопасной работы с cookies VK.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional

from src.config import VK_COOKIES, VK_COOKIES_ENABLED

logger = logging.getLogger(__name__)
_WARNED_KEYS: set[str] = set()


def _warn_once(key: str, message: str, *args: object) -> None:
    """Логирует предупреждение только один раз для указанного ключа."""
    if key in _WARNED_KEYS:
        return
    _WARNED_KEYS.add(key)
    logger.warning(message, *args)


def _looks_like_placeholder(path: Path) -> bool:
    """
    Проверяет, похож ли файл на заглушку (пустой или без cookie-строк).
    """
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return True

    if not content.strip():
        return True

    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        return True

    cookie_lines = []
    for line in lines:
        if "\t" not in line:
            continue
        if line.startswith("#") and not line.startswith("#HttpOnly_"):
            continue
        cookie_lines.append(line)
    return len(cookie_lines) == 0


def _resolve_valid_cookie_path() -> Optional[Path]:
    """
    Возвращает валидный путь cookies-файла VK или None.
    """
    if not VK_COOKIES_ENABLED:
        return None

    if not isinstance(VK_COOKIES, Path):
        _warn_once("vk-cookies-path-not-set", "VK cookies enabled, but VK_COOKIES_PATH is not set.")
        return None

    if not VK_COOKIES.exists():
        _warn_once(
            f"vk-cookies-missing:{VK_COOKIES}",
            "VK cookies enabled, but cookie file does not exist: %s",
            VK_COOKIES,
        )
        return None

    if _looks_like_placeholder(VK_COOKIES):
        _warn_once(
            f"vk-cookies-placeholder:{VK_COOKIES}",
            "VK cookies file looks like a placeholder and will be ignored: %s",
            VK_COOKIES,
        )
        return None

    return VK_COOKIES


def build_vk_request_cookies() -> Dict[str, str]:
    """
    Загружает cookies из Netscape-файла в словарь для HTTP-запросов.
    """
    cookies_path = _resolve_valid_cookie_path()
    if not cookies_path:
        return {}

    cookies: Dict[str, str] = {}
    try:
        for raw_line in cookies_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("#HttpOnly_"):
                line = line[len("#HttpOnly_"):]
            elif line.startswith("#"):
                continue

            parts = line.split("\t")
            if len(parts) < 7:
                continue

            name = parts[5].strip()
            value = parts[6].strip()
            if not name:
                continue
            cookies[name] = value
    except Exception as exc:
        _warn_once(
            f"vk-cookies-parse-failed:{cookies_path}",
            "Failed to parse VK cookies file %s: %s",
            cookies_path,
            exc,
        )
        return {}

    if not cookies:
        _warn_once(
            f"vk-cookies-empty:{cookies_path}",
            "VK cookies file is valid but contains no parsable cookies: %s",
            cookies_path,
        )
    return cookies


def build_vk_cookiefile_opt() -> Dict[str, str]:
    """
    Возвращает cookiefile-опцию для редкого fallback через yt-dlp.
    """
    cookies_path = _resolve_valid_cookie_path()
    if not cookies_path:
        return {}
    return {"cookiefile": str(cookies_path)}
