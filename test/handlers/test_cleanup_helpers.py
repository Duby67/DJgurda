"""Unit-тесты cleanup-контракта MediaResult."""

from __future__ import annotations

import sys
from pathlib import Path

# test/handlers/test_cleanup_helpers.py -> project root это parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.handlers.contracts import (
    AttachmentKind,
    AudioAttachment,
    ContentType,
    MediaAttachment,
    MediaResult,
)


def test_iter_cleanup_paths_includes_audios_list() -> None:
    """
    Typed cleanup должен учитывать список `audios`.
    """
    result = MediaResult(
        content_type=ContentType.MEDIA_GROUP,
        source_name="Instagram",
        original_url="https://instagram.com/p/demo",
        context="unit-test",
        media_group=(
            MediaAttachment(
                kind=AttachmentKind.PHOTO,
                file_path=Path("photo.jpg"),
            ),
        ),
        audios=(
            AudioAttachment(file_path=Path("a1.m4a")),
            AudioAttachment(
                file_path=Path("a2.m4a"),
                thumbnail_path=Path("a2.jpg"),
            ),
        ),
        cleanup_paths=(Path("a1.m4a"),),
    )

    paths = set(result.iter_cleanup_paths())
    assert Path("photo.jpg") in paths
    assert Path("a1.m4a") in paths
    assert Path("a2.m4a") in paths
    assert Path("a2.jpg") in paths
