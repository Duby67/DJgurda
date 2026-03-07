"""
Утилиты для безопасного подключения Instagram cookies в yt-dlp.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

from src.config import INSTAGRAM_COOKIES, INSTAGRAM_COOKIES_ENABLED

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

    cookie_lines = [
        line
        for line in lines
        if not line.startswith("#") and "\t" in line
    ]
    return len(cookie_lines) == 0


def build_instagram_cookie_opts() -> Dict[str, Any]:
    """
    Возвращает `cookiefile` для yt-dlp в безопасном auto-режиме.

    Поведение:
    - `INSTAGRAM_COOKIES_ENABLED=false` -> cookies принудительно отключены;
    - `INSTAGRAM_COOKIES_ENABLED=true` -> используется валидный файл cookies;
    - отсутствующий/пустой/заглушечный файл автоматически игнорируется.
    """
    if not INSTAGRAM_COOKIES_ENABLED:
        return {}

    if not isinstance(INSTAGRAM_COOKIES, Path):
        logger.warning("Instagram cookies enabled, but INSTAGRAM_COOKIES_PATH is not set.")
        return {}

    if not INSTAGRAM_COOKIES.exists():
        logger.warning(
            "Instagram cookies enabled, but cookie file does not exist: %s",
            INSTAGRAM_COOKIES,
        )
        return {}

    if _looks_like_placeholder(INSTAGRAM_COOKIES):
        logger.warning(
            "Instagram cookies file looks like a placeholder and will be ignored: %s",
            INSTAGRAM_COOKIES,
        )
        return {}

    return {"cookiefile": str(INSTAGRAM_COOKIES)}

