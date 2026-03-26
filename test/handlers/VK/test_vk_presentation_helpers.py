"""Unit-tests for VK presentation helpers (post/profile/community)."""

from __future__ import annotations

import asyncio
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
from src.handlers.contracts import AttachmentKind


class _DummyRequestContext:
    """Минимальный request-context для helper unit-tests без сети."""

    DEFAULT_USER_AGENT = "test-agent"

    def __init__(
        self,
        *,
        html_text: str = "",
        ld_objects: list[dict[str, Any]] | None = None,
    ) -> None:
        self._html_text = html_text
        self._ld_objects = ld_objects or []

    def _extract_ld_objects(self, html_text: str) -> list[dict[str, Any]]:  # noqa: ARG002
        return list(self._ld_objects)

    @staticmethod
    def _strip_html(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        return BeautifulSoup(value, "html.parser").get_text(" ", strip=True) or None

    @staticmethod
    def _first_non_empty(*values: Any) -> str | None:
        for value in values:
            if isinstance(value, str):
                cleaned = value.strip()
                if cleaned:
                    return cleaned
        return None

    @staticmethod
    def build_browser_headers(*, referer: str | None = None) -> dict[str, str]:  # noqa: ARG004
        return {"User-Agent": "test-agent"}

    @staticmethod
    def _build_vk_cookie_opts() -> dict[str, str]:
        return {}

    @staticmethod
    def _normalize_vk_url(url: str) -> str:
        return url

    async def _fetch_html(self, session: Any, url: str) -> str | None:  # noqa: ARG002
        return self._html_text


class _DummyMediaGateway:
    """Минимальный gateway-заглушка для helper unit-tests."""

    def __init__(self, tmp_path: Path | None = None, *, payload: list[dict[str, Any]] | None = None) -> None:
        self.temp_dir = tmp_path or Path.cwd()
        self.audio_limit = 10_000_000
        self.photo_limit = 10_000_000
        self._payload = payload or []

    def _generate_unique_path(self, identifier: str, suffix: str = "") -> Path:
        return self.temp_dir / f"{identifier}{suffix}"

    async def _download_thumbnail(
        self,
        url: str,
        dest_path: Path,
        size_limit: int | None = None,  # noqa: ARG002
    ) -> bool:
        dest_path.write_bytes(url.encode("utf-8"))
        return True

    async def _download_media_group(
        self,
        url: str,  # noqa: ARG002
        ydl_opts: dict[str, Any],  # noqa: ARG002
        *,
        group_id: str | None = None,  # noqa: ARG002
        size_limit: int | None = None,  # noqa: ARG002
    ) -> list[dict[str, Any]]:
        return list(self._payload)


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


def test_vk_post_normalize_post_text_decodes_html_entities() -> None:
    """HTML entities из embedded VK payload должны превращаться обратно в emoji для lead_text."""
    post = VKPost(request_context=_DummyRequestContext(), media_gateway=_DummyMediaGateway())

    normalized = post._normalize_post_text("&#127756; Космос &#10024;")

    assert normalized == "🌌 Космос ✨"


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


def test_vk_post_process_prefers_embedded_original_photo_for_single_photo_payload(tmp_path: Path) -> None:
    """Одиночный placeholder-photo должен заменяться на embedded orig_photo из wall payload."""
    placeholder_path = tmp_path / "placeholder.jpg"
    placeholder_path.write_bytes(b"placeholder-photo")
    html_text = (
        "<html><head><title>Пост | ВКонтакте</title></head><body></body></html>"
        f'{VKPost.EMBEDDED_POST_MARKER},'
        '"groups":[{"id":99353432,"name":"КОСМОС","screen_name":"spaces"}],'
        '"text":"&#127756; Текст поста",'
        '"id":629095,'
        '"orig_photo":{"url":"https:\\/\\/example.com\\/real-post.jpg"}'
    )
    request_context = _DummyRequestContext(html_text=html_text)
    media_gateway = _DummyMediaGateway(
        tmp_path,
        payload=[{"type": "photo", "file_path": placeholder_path}],
    )
    post = VKPost(request_context=request_context, media_gateway=media_gateway)

    result = asyncio.run(
        post.process(
            session=None,
            original_url="https://vk.com/wall-99353432_629095",
            context="ctx",
            owner_id="-99353432",
            post_id="629095",
        )
    )

    assert result is not None
    assert result.media_group
    assert len(result.media_group) == 1
    assert result.media_group[0].kind == AttachmentKind.PHOTO
    assert result.media_group[0].file_path.read_bytes() == b"https://example.com/real-post.jpg"
    assert placeholder_path in result.cleanup_paths
