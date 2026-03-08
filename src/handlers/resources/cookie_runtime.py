"""
Утилиты для безопасной подготовки cookie-файлов под yt-dlp.
"""

from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path
from typing import Optional

from src.config import PROJECT_TEMP_DIR

logger = logging.getLogger(__name__)

_YTDLP_COOKIE_RUNTIME_DIR = PROJECT_TEMP_DIR / "_yt_dlp_cookies"
_MAX_RUNTIME_COPIES_PER_PROVIDER = 20


def _prune_old_runtime_copies(provider_key: str) -> None:
    """
    Ограничивает число runtime-копий cookies для одного провайдера.
    """
    try:
        candidates = sorted(
            _YTDLP_COOKIE_RUNTIME_DIR.glob(f"{provider_key}_*.txt"),
            key=lambda path: path.stat().st_mtime if path.exists() else 0,
            reverse=True,
        )
    except Exception:
        return

    for stale_path in candidates[_MAX_RUNTIME_COPIES_PER_PROVIDER:]:
        try:
            stale_path.unlink(missing_ok=True)
        except Exception:
            continue


def prepare_cookiefile_for_ytdlp(source_path: Path, provider_key: str) -> Optional[Path]:
    """
    Создает рабочую копию cookie-файла для yt-dlp и возвращает путь к ней.

    Оригинальный cookie-файл не передается в yt-dlp напрямую, чтобы исключить
    его изменение сторонним инструментом.
    """
    if not isinstance(source_path, Path):
        return None

    safe_provider_key = (provider_key or "provider").strip().lower().replace(" ", "_")
    if not safe_provider_key:
        safe_provider_key = "provider"

    try:
        _YTDLP_COOKIE_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        runtime_copy_path = _YTDLP_COOKIE_RUNTIME_DIR / f"{safe_provider_key}_{uuid.uuid4().hex[:12]}.txt"
        shutil.copy2(source_path, runtime_copy_path)
        _prune_old_runtime_copies(safe_provider_key)
        return runtime_copy_path
    except Exception as exc:
        logger.warning(
            "Failed to prepare temporary cookies copy for %s (%s): %s",
            safe_provider_key,
            source_path,
            exc,
        )
        return None
