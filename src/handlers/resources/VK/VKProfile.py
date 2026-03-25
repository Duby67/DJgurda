"""
Процессор VK profile/community card.
"""

from __future__ import annotations

import html
import logging
from typing import Any, Optional

import aiohttp
from bs4 import BeautifulSoup

from src.handlers.contracts import ContentType, MediaResult
from .VKDependencies import VKMediaGatewayProtocol, VKRequestContextProtocol

logger = logging.getLogger(__name__)


class VKProfile:
    """Процессор profile/community страницы VK."""

    def __init__(
        self,
        *,
        request_context: VKRequestContextProtocol,
        media_gateway: VKMediaGatewayProtocol,
    ) -> None:
        self._request_context = request_context
        self._media_gateway = media_gateway

    def __getattr__(self, name: str) -> Any:
        if hasattr(self._request_context, name):
            return getattr(self._request_context, name)
        if hasattr(self._media_gateway, name):
            return getattr(self._media_gateway, name)
        raise AttributeError(name)

    @staticmethod
    def _build_caption(title: str, canonical_url: str, description: Optional[str]) -> str:
        """Формирует компактную profile-card подпись."""
        safe_title = html.escape(title)
        safe_url = html.escape(canonical_url, quote=True)
        lines = [f'<a href="{safe_url}"><b>{safe_title}</b></a>']
        if isinstance(description, str) and description.strip():
            normalized = " ".join(description.split())
            if len(normalized) > 260:
                normalized = normalized[:260].rstrip() + "..."
            lines.append(f"<i>{html.escape(normalized)}</i>")
        return "\n".join(lines)

    async def process(
        self,
        session: aiohttp.ClientSession,
        original_url: str,
        context: str,
        canonical_url: str,
        screen_name: str,
    ) -> Optional[MediaResult]:
        """Возвращает profile-card для user/community URL."""
        html_text = await self._fetch_html(session, canonical_url)
        if not html_text:
            return None

        soup = BeautifulSoup(html_text, "html.parser")
        title = self._first_non_empty(
            self._strip_html(soup.title.get_text(strip=True) if soup.title else None),
            screen_name,
            "VK Profile",
        ) or "VK Profile"
        if title == "ВКонтакте" and screen_name:
            title = screen_name

        description = None
        og_description = soup.find("meta", attrs={"property": "og:description"})
        if og_description:
            description = self._first_non_empty(og_description.get("content"))

        avatar_url = None
        og_image = soup.find("meta", attrs={"property": "og:image"})
        if og_image:
            avatar_url = self._extract_first_http_url(og_image.get("content"))

        avatar_path = None
        if avatar_url:
            avatar_path = self._generate_unique_path(f"{screen_name}_avatar", suffix=".jpg")
            if not await self._download_thumbnail(avatar_url, avatar_path, self.photo_limit):
                avatar_path = None

        return MediaResult(
            content_type=ContentType.PROFILE,
            source_name="VK",
            original_url=original_url,
            context=context,
            title=title,
            uploader=screen_name,
            main_file_path=avatar_path,
            caption_text=self._build_caption(title=title, canonical_url=canonical_url, description=description),
        )
