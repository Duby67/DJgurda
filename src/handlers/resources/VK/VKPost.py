"""
Процессор VK wall posts.
"""

from __future__ import annotations

import html
import logging
import re
from typing import Any, Optional

import aiohttp

from src.handlers.contracts import AttachmentKind, ContentType, MediaAttachment, MediaResult
from .VKDependencies import VKMediaGatewayProtocol, VKRequestContextProtocol

logger = logging.getLogger(__name__)


class VKPost:
    """Процессор wall post с best-effort media-group extraction."""

    IMAGE_URL_PATTERN = re.compile(r'https?://[^"\']+\.(?:jpg|jpeg|png)[^"\']*', re.IGNORECASE)

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
    def _build_caption(title: str, canonical_url: str) -> str:
        """Формирует caption wall post."""
        safe_title = html.escape(title)
        safe_url = html.escape(canonical_url, quote=True)
        return f'<a href="{safe_url}"><b>{safe_title}</b></a>'

    async def process(
        self,
        session: aiohttp.ClientSession,
        original_url: str,
        context: str,
        owner_id: str,
        post_id: str,
    ) -> Optional[MediaResult]:
        """Возвращает media_group для wall post."""
        canonical_url = f"https://vk.com/wall{owner_id}_{post_id}"
        html_text = await self._fetch_html(session, canonical_url)
        if not html_text:
            return None

        title = "VK Wall Post"
        title_match = re.search(r"<title>(?P<title>[^<]+)</title>", html_text, re.IGNORECASE)
        if title_match:
            title = self._first_non_empty(self._strip_html(title_match.group("title")), title) or title

        media_group: list[MediaAttachment] = []
        seen_urls: set[str] = set()
        for image_url in self.IMAGE_URL_PATTERN.findall(html_text):
            normalized_url = image_url.replace("http://", "https://", 1)
            if normalized_url in seen_urls:
                continue
            seen_urls.add(normalized_url)
            file_path = self._generate_unique_path(f"wall{owner_id}_{post_id}_{len(media_group)}", suffix=".jpg")
            if await self._download_thumbnail(normalized_url, file_path, self.photo_limit):
                media_group.append(MediaAttachment(kind=AttachmentKind.PHOTO, file_path=file_path))
            if media_group:
                break

        if not media_group:
            return None

        return MediaResult(
            content_type=ContentType.MEDIA_GROUP,
            source_name="VK",
            original_url=original_url,
            context=context,
            title=title,
            uploader=owner_id,
            caption_text=self._build_caption(title=title, canonical_url=canonical_url),
            media_group=tuple(media_group),
        )
