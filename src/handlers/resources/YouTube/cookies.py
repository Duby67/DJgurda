"""
Утилиты для безопасного подключения YouTube cookies в yt-dlp.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

from src.config import YOUTUBE_COOKIES, YOUTUBE_COOKIES_ENABLED

logger = logging.getLogger(__name__)


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
    Возвращает `cookiefile` для yt-dlp только при явном включении и валидном файле.
    """
    if not YOUTUBE_COOKIES_ENABLED:
        return {}

    if not isinstance(YOUTUBE_COOKIES, Path):
        logger.warning("YouTube cookies enabled, but YOUTUBE_COOKIES_PATH is not set.")
        return {}

    if not YOUTUBE_COOKIES.exists():
        logger.warning("YouTube cookies enabled, but cookie file does not exist: %s", YOUTUBE_COOKIES)
        return {}

    if _looks_like_placeholder(YOUTUBE_COOKIES):
        logger.warning(
            "YouTube cookies file looks like a placeholder and will be ignored: %s",
            YOUTUBE_COOKIES,
        )
        return {}

    return {"cookiefile": str(YOUTUBE_COOKIES)}

