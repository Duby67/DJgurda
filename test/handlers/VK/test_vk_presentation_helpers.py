"""Unit-tests for VK presentation helpers (post/profile/community)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

# test/handlers/VK/test_vk_presentation_helpers.py -> project root это parents[3]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Минимальные env для загрузки src.config.
os.environ.setdefault("BOT_DB_PATH", str(PROJECT_ROOT / "src" / "data" / "db" / "bot.db"))
os.environ.setdefault("BOT_VERSION", "local-test")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("BOT_TOKEN", "local-test-token")
os.environ.setdefault("YANDEX_MUSIC_TOKEN", "local-test-token")

from src.handlers.resources.VK.VKPost import VKPost
from src.handlers.resources.VK.VKProfile import VKProfile


class _DummyRequestContext:
    """Минимальный request-context для helper unit-tests без сети."""

    DEFAULT_USER_AGENT = "test-agent"

    def __init__(self, *, ld_objects: list[dict[str, Any]] | None = None) -> None:
        self._ld_objects = ld_objects or []

    def _extract_ld_objects(self, html_text: str) -> list[dict[str, Any]]:  # noqa: ARG002
        return list(self._ld_objects)

    @staticmethod
    def _strip_html(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        return BeautifulSoup(value, "html.parser").get_text(" ", strip=True) or None


class _DummyMediaGateway:
    """Минимальный gateway-заглушка для helper unit-tests."""


def test_vk_post_extract_post_text_prefers_richer_candidate() -> None:
    """VKPost should pick the richest post text candidate from available sources."""
    request_context = _DummyRequestContext(
        ld_objects=[
            {"description": "Короткое описание"},
            {"articleBody": "Большой текст поста с полезными деталями и несколькими фактами"},
        ]
    )
    post = VKPost(request_context=request_context, media_gateway=_DummyMediaGateway())
    html_text = (
        "<html><head><title>Пост | ВКонтакте</title></head>"
        "<body><div class='wall_post_text'>Короткий текст</div></body></html>"
    )
    soup = BeautifulSoup(html_text, "html.parser")

    extracted = post._extract_post_text(soup, html_text, title="Пост")

    assert extracted is not None
    assert "Большой текст поста" in extracted


def test_vk_profile_caption_contains_hyperlink_nickname_and_public_info() -> None:
    """Profile/community caption should include link, nickname and public info rows."""
    caption = VKProfile._build_caption(
        title="VK Spaces | ВКонтакте",
        canonical_url="https://vk.com/spaces",
        screen_name="spaces",
        info_lines=("Открытая информация", "Контакты"),
    )

    assert '<a href="https://vk.com/spaces"><b>VK Spaces</b></a>' in caption
    assert "@spaces" in caption
    assert "• Открытая информация" in caption
    assert "• Контакты" in caption
