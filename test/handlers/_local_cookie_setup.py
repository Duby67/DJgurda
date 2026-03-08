"""
Утилита для локальных smoke-тестов handlers:
копирует cookies из local/cookies в src/data/cookies перед запуском проверок.
"""

from __future__ import annotations

import shutil
from pathlib import Path

COOKIE_FILENAMES = (
    "youtube_cookies.txt",
    "instagram_cookies.txt",
    "vk.com_cookies.txt",
)


def prepare_local_cookie_runtime(project_root: Path) -> None:
    """
    Подготавливает рабочие cookies для локальных smoke-тестов.

    Источник:
    - <project_root>/local/cookies

    Приемник:
    - <project_root>/src/data/cookies
    """
    source_dir = project_root / "local" / "cookies"
    target_dir = project_root / "src" / "data" / "cookies"
    target_dir.mkdir(parents=True, exist_ok=True)

    if not source_dir.is_dir():
        return

    for filename in COOKIE_FILENAMES:
        source_path = source_dir / filename
        if not source_path.is_file():
            continue

        # Пустые файлы считаем заглушкой и не переносим в рабочую директорию.
        if source_path.stat().st_size <= 0:
            continue

        target_path = target_dir / filename
        shutil.copy2(source_path, target_path)
