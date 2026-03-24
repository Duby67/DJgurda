"""Unit-тесты для безопасной сборки caption."""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from types import SimpleNamespace

# test/bot/processing/test_media_caption.py -> project root это parents[3]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Минимальные env для загрузки src.config.
os.environ.setdefault("BOT_DB_PATH", str(PROJECT_ROOT / "src" / "data" / "db" / "bot.db"))
os.environ.setdefault("BOT_VERSION", "local-test")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("BOT_TOKEN", "local-test-token")
os.environ.setdefault("YANDEX_MUSIC_TOKEN", "local-test-token")
os.environ.setdefault("YOUTUBE_COOKIES_ENABLED", "false")

messages_module = importlib.import_module("src.utils.messages")
link_extractor_module = importlib.import_module("src.bot.processing.link_extractor")

from src.config import MAX_CAPTION
from src.handlers.contracts import ContentType, MediaResult

build_caption = messages_module.build_caption
get_user_link = link_extractor_module.get_user_link


class FakeHandler:
    """Минимальный handler для caption-тестов."""

    source_name = "YouTube"


def test_build_caption_truncates_plain_text_without_breaking_html() -> None:
    """Длинные plain-text секции сокращаются, а HTML-анкоры остаются валидными."""
    user_context = " ".join(
        [
            "Контекст",
            "<опасный>",
            "& еще один фрагмент",
        ]
        * 60
    )
    media_result = MediaResult(
        content_type=ContentType.VIDEO,
        source_name="YouTube",
        original_url="https://example.com/watch?v=123",
        context=user_context,
        title=" ".join(["Заголовок с <html> & символами"] * 45),
        uploader=" ".join(["Автор & Co"] * 35),
    )
    user_link = get_user_link(
        SimpleNamespace(
            id=101,
            username="captions",
            full_name=" ".join(["Очень длинное имя пользователя <и> & символами"] * 30),
        )
    )

    caption = build_caption(
        user_context=user_context,
        media_result=media_result,
        user_link=user_link,
        url="https://example.com/watch?v=123&ref=test",
        handler=FakeHandler(),
    )

    assert len(caption) <= MAX_CAPTION
    assert caption.count("<a href=") == 2
    assert caption.count("</a>") == 2
    assert "https://example.com/watch?v=123&amp;ref=test" in caption
    assert "..." in caption


def test_build_caption_truncates_user_link_anchor_safely() -> None:
    """Очень длинный user_link укорачивается без поломки anchor tag."""
    media_result = MediaResult(
        content_type=ContentType.VIDEO,
        source_name="TikTok",
        original_url="https://example.com/watch",
        context="",
        title="Короткий заголовок",
        uploader=None,
    )
    user_link = get_user_link(
        SimpleNamespace(
            id=202,
            username=None,
            full_name=" ".join(["Пользователь с очень длинным именем & <html>"] * 80),
        )
    )

    caption = build_caption(
        user_context="",
        media_result=media_result,
        user_link=user_link,
        url="https://example.com/watch",
        handler=SimpleNamespace(source_name="TikTok"),
    )

    assert len(caption) <= MAX_CAPTION
    assert caption.count("<a href=") == 2
    assert caption.count("</a>") == 2
    assert "tg://user?id=202" in caption
    assert "TikTok" in caption
    assert "..." in caption
