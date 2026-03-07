"""Unit-тесты очистки временных файлов в BaseHandler."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# test/handlers/test_cleanup_helpers.py -> project root это parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Минимальные env для загрузки src.config.
os.environ.setdefault("BOT_DB_PATH", str(PROJECT_ROOT / "src" / "data" / "db" / "bot.db"))
os.environ.setdefault("BOT_VERSION", "local-test")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("BOT_TOKEN", "local-test-token")
os.environ.setdefault("YANDEX_MUSIC_TOKEN", "local-test-token")
os.environ.setdefault("YOUTUBE_COOKIES_ENABLED", "false")

from src.handlers.resources.Instagram.InstagramHandler import InstagramHandler


def test_collect_paths_includes_audios_list() -> None:
    """
    Base cleanup должен учитывать список `audios` в file_info.
    """
    handler = InstagramHandler()
    file_info = {
        "type": "media_group",
        "files": [],
        "audios": [
            {"file_path": Path("a1.m4a")},
            {"file_path": Path("a2.m4a"), "thumbnail_path": Path("a2.jpg")},
        ],
    }

    paths = set(handler._collect_paths_for_cleanup(file_info))
    assert Path("a1.m4a") in paths
    assert Path("a2.m4a") in paths
    assert Path("a2.jpg") in paths

