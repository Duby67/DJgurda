"""
Утилиты для подготовки и очистки runtime-хранилища.

Содержит единые функции для работы с директориями БД и временных файлов.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Iterable

from src.config import DB_FILE, PROJECT_TEMP_DIR

logger = logging.getLogger(__name__)


def _iter_temp_files() -> Iterable[Path]:
    """Итерирует все файлы во временной директории."""
    if not PROJECT_TEMP_DIR.exists():
        return ()
    return (path for path in PROJECT_TEMP_DIR.rglob("*") if path.is_file())


def _prune_empty_dirs(root_dir: Path) -> int:
    """Удаляет пустые директории внутри `root_dir` и возвращает их количество."""
    if not root_dir.exists():
        return 0

    removed = 0
    # Идем с конца, чтобы сначала удалить глубокие вложенные папки.
    for path in sorted((p for p in root_dir.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        try:
            path.rmdir()
            removed += 1
        except OSError:
            continue
    return removed


def ensure_runtime_storage(handler_names: Iterable[str]) -> None:
    """
    Готовит runtime-директории:
    - родительскую директорию БД;
    - корневую папку временных файлов;
    - отдельные temp-папки для каждого активного handler.
    """
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROJECT_TEMP_DIR.mkdir(parents=True, exist_ok=True)

    created_handler_dirs = 0
    for handler_name in sorted({name.strip() for name in handler_names if name and name.strip()}):
        (PROJECT_TEMP_DIR / handler_name).mkdir(parents=True, exist_ok=True)
        created_handler_dirs += 1

    logger.info(
        "Runtime storage prepared: db_dir=%s, temp_root=%s, handler_dirs=%s",
        DB_FILE.parent,
        PROJECT_TEMP_DIR,
        created_handler_dirs,
    )


def cleanup_expired_temp_files(max_age_seconds: int) -> int:
    """Удаляет устаревшие временные файлы старше `max_age_seconds`."""
    if max_age_seconds < 0:
        raise ValueError("max_age_seconds must be >= 0")

    now = time.time()
    removed_files = 0
    for file_path in _iter_temp_files():
        try:
            if (now - file_path.stat().st_mtime) > max_age_seconds:
                file_path.unlink(missing_ok=True)
                removed_files += 1
        except Exception as exc:
            logger.warning("Failed to remove expired temp file %s: %s", file_path, exc)

    logger.info("Expired temp cleanup finished: files_removed=%s", removed_files)
    return removed_files


def cleanup_all_temp_files() -> int:
    """Удаляет все временные файлы из runtime-директории."""
    removed_files = 0
    for file_path in _iter_temp_files():
        try:
            file_path.unlink(missing_ok=True)
            removed_files += 1
        except Exception as exc:
            logger.warning("Failed to remove temp file %s: %s", file_path, exc)

    removed_dirs = _prune_empty_dirs(PROJECT_TEMP_DIR)
    logger.info("Full temp cleanup finished: files_removed=%s, empty_dirs_removed=%s", removed_files, removed_dirs)
    return removed_files
