"""
Утилиты для безопасного подключения YouTube cookies в yt-dlp.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

from src.config import YOUTUBE_COOKIES, YOUTUBE_COOKIES_ENABLED
from src.handlers.resources.cookie_runtime import prepare_cookiefile_for_ytdlp

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

    # Разрешаем стандартный заголовок Netscape и ищем хотя бы одну cookie-строку.
    cookie_lines = [
        line
        for line in lines
        if not line.startswith("#") and "\t" in line
    ]
    return len(cookie_lines) == 0


def build_youtube_cookie_opts() -> Dict[str, Any]:
    """
    Возвращает `cookiefile` для yt-dlp в безопасном auto-режиме.

    Поведение:
    - `YOUTUBE_COOKIES_ENABLED=false` -> cookies принудительно отключены;
    - `YOUTUBE_COOKIES_ENABLED=true` -> используется валидный файл cookies;
    - отсутствующий/пустой/заглушечный файл автоматически игнорируется.
    """
    if not YOUTUBE_COOKIES_ENABLED:
        return {}

    if not isinstance(YOUTUBE_COOKIES, Path):
        _warn_once("youtube-cookies-path-not-set", "YouTube cookies enabled, but YOUTUBE_COOKIES_PATH is not set.")
        return {}

    if not YOUTUBE_COOKIES.exists():
        _warn_once(
            f"youtube-cookies-missing:{YOUTUBE_COOKIES}",
            "YouTube cookies enabled, but cookie file does not exist: %s",
            YOUTUBE_COOKIES,
        )
        return {}

    if _looks_like_placeholder(YOUTUBE_COOKIES):
        _warn_once(
            f"youtube-cookies-placeholder:{YOUTUBE_COOKIES}",
            "YouTube cookies file looks like a placeholder and will be ignored: %s",
            YOUTUBE_COOKIES,
        )
        return {}

    runtime_cookie_path = prepare_cookiefile_for_ytdlp(YOUTUBE_COOKIES, provider_key="youtube")
    if not isinstance(runtime_cookie_path, Path):
        _warn_once(
            f"youtube-cookies-runtime-copy-failed:{YOUTUBE_COOKIES}",
            "YouTube cookies file is valid, but runtime copy for yt-dlp failed and will be ignored: %s",
            YOUTUBE_COOKIES,
        )
        return {}

    return {"cookiefile": str(runtime_cookie_path)}
