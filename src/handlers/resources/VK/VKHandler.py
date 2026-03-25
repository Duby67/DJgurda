"""
Главный обработчик VK (audio + playlist + clip + post + profile/community).
"""

from __future__ import annotations

import logging
import re
from typing import Optional

import aiohttp

from src.config import PROJECT_TEMP_DIR
from src.handlers.base import BaseHandler
from src.handlers.contracts import MediaResult

from .VKAudio import VKAudio
from .VKClip import VKClip
from .VKDependencies import VKMediaGateway, VKRequestContext
from .VKPlaylist import VKPlaylist
from .VKPost import VKPost
from .VKProfile import VKProfile
from .VKUrlService import VKUrlService

logger = logging.getLogger(__name__)


class VKHandler(BaseHandler):
    """
    Асинхронный обработчик VK:
    - одиночный трек (`audio`);
    - плейлист (`playlist`).
    - clip (`video`);
    - wall post (`media_group`);
    - account/community (`profile`).
    """

    PATTERN = re.compile(
        r"https?://(?:www\.|m\.)?(?:vk\.com|vk\.ru|vkvideo\.ru)/"
        r"(?:"
        r"audio-?\d+_\d+(?:_[A-Za-z0-9]+)?|"
        r"music/playlist/-?\d+_\d+(?:_[A-Za-z0-9]+)?|"
        r"clip-?\d+_\d+|"
        r"wall-?\d+_\d+|"
        r"id\d+|"
        r"[A-Za-z0-9_.-]+"
        r")"
        r"(?:/?(?:\?.*)?)?$",
        re.IGNORECASE,
    )

    def __init__(self) -> None:
        self._runtime_dir = PROJECT_TEMP_DIR / self.__class__.__name__
        self._runtime_dir.mkdir(parents=True, exist_ok=True)

        self._url_service = VKUrlService()
        self._request_context = VKRequestContext(runtime_dir=self._runtime_dir)
        self._media_gateway = VKMediaGateway(runtime_dir=self._runtime_dir)

        self._audio_processor = VKAudio(
            request_context=self._request_context,
            media_gateway=self._media_gateway,
        )
        self._clip_processor = VKClip(
            request_context=self._request_context,
            media_gateway=self._media_gateway,
        )
        self._playlist_processor = VKPlaylist(
            request_context=self._request_context,
            media_gateway=self._media_gateway,
        )
        self._post_processor = VKPost(
            request_context=self._request_context,
            media_gateway=self._media_gateway,
        )
        self._profile_processor = VKProfile(
            request_context=self._request_context,
            media_gateway=self._media_gateway,
        )

    @property
    def pattern(self) -> re.Pattern:
        """Возвращает паттерн распознавания VK URL."""
        return self.PATTERN

    @property
    def source_name(self) -> str:
        """Возвращает имя источника."""
        return "VK"

    async def process(
        self,
        url: str,
        context: str,
        resolved_url: Optional[str] = None,
    ) -> Optional[MediaResult]:
        """Основной вход обработчика VK."""
        target_url = self._url_service.normalize(resolved_url or url)
        content_type, content_match = self._url_service.detect_content_type(target_url)
        if not content_type or not content_match:
            logger.warning("Unsupported VK URL type: %s", target_url)
            return None

        timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=30)
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "ru,en-US;q=0.9,en;q=0.8",
            "Referer": "https://vk.com/",
            "Origin": "https://vk.com",
            "X-Requested-With": "XMLHttpRequest",
        }

        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            if content_type == "audio":
                return await self._audio_processor.process(
                    session=session,
                    original_url=url,
                    context=context,
                    owner_id=content_match.group("owner"),
                    audio_id=content_match.group("audio"),
                    access_hash=content_match.group("access_hash"),
                )

            if content_type == "playlist":
                return await self._playlist_processor.process(
                    session=session,
                    original_url=url,
                    context=context,
                    owner_id=content_match.group("owner"),
                    playlist_id=content_match.group("playlist"),
                    access_hash=content_match.group("access_hash"),
                )

            if content_type == "clip":
                return await self._clip_processor.process(
                    session=session,
                    original_url=url,
                    context=context,
                    owner_id=content_match.group("owner"),
                    clip_id=content_match.group("clip"),
                )

            if content_type == "post":
                return await self._post_processor.process(
                    session=session,
                    original_url=url,
                    context=context,
                    owner_id=content_match.group("owner"),
                    post_id=content_match.group("post"),
                )

            if content_type == "profile":
                screen_name = (
                    content_match.groupdict().get("screen_name")
                    or content_match.groupdict().get("profile_id")
                    or target_url.rsplit("/", 1)[-1]
                )
                return await self._profile_processor.process(
                    session=session,
                    original_url=url,
                    context=context,
                    canonical_url=target_url,
                    screen_name=screen_name,
                )

        logger.warning("VK content type is not supported by process() branch: %s", content_type)
        return None
