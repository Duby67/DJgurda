"""
Процессор VK clip/video.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Optional

import aiohttp
import yt_dlp

from src.handlers.contracts import ContentType, MediaResult
from src.utils.cookies import cleanup_runtime_cookiefile
from .VKDependencies import VKMediaGatewayProtocol, VKRequestContextProtocol

logger = logging.getLogger(__name__)


class VKClip:
    """Процессор для скачивания одиночного VK clip."""

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

    async def _download_clip(
        self,
        canonical_url: str,
        clip_token: str,
    ) -> tuple[Optional[Path], dict[str, Any] | None]:
        """Скачивает клип через yt-dlp с cookies и bounded opts."""
        output_template = str(self._generate_unique_path(clip_token, suffix="")) + ".%(ext)s"
        ydl_opts = self._build_ytdlp_opts(
            {
                "noplaylist": True,
                "format": "mp4/bestvideo+bestaudio/best",
                "outtmpl": output_template,
                "retries": 1,
                "fragment_retries": 1,
                "quiet": True,
                "no_warnings": True,
            }
        )
        ydl_opts.update(self._build_vk_cookie_opts())
        cookiefile_path = ydl_opts.get("cookiefile")

        def _download() -> tuple[Optional[Path], dict[str, Any] | None]:
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(canonical_url, download=True)
                    if not isinstance(info, dict):
                        return None, None
                    prepared = Path(ydl.prepare_filename(info))
                    return prepared, info
            finally:
                cleanup_runtime_cookiefile(cookiefile_path)

        try:
            downloaded_path, info = await asyncio.to_thread(_download)
        except Exception as exc:
            logger.warning("VK clip download failed for %s: %s", canonical_url, exc)
            return None, None

        if isinstance(downloaded_path, Path) and downloaded_path.exists() and downloaded_path.stat().st_size > 0:
            return downloaded_path, info

        candidates = sorted(
            self.temp_dir.glob(f"{Path(output_template).stem}.*"),
            key=lambda item: item.stat().st_mtime if item.exists() else 0,
            reverse=True,
        )
        final_path = next((candidate for candidate in candidates if candidate.exists() and candidate.stat().st_size > 0), None)
        return final_path, info

    async def process(
        self,
        session: aiohttp.ClientSession,
        original_url: str,
        context: str,
        owner_id: str,
        clip_id: str,
    ) -> Optional[MediaResult]:
        """Скачивает clip и возвращает video MediaResult."""
        canonical_url = f"https://vkvideo.ru/clip{owner_id}_{clip_id}"
        clip_token = f"clip{owner_id}_{clip_id}"
        file_path, info = await self._download_clip(canonical_url, clip_token=clip_token)
        if not file_path:
            return None

        title = self._first_non_empty(
            (info or {}).get("title") if isinstance(info, dict) else None,
            f"VK Clip {owner_id}_{clip_id}",
        ) or f"VK Clip {owner_id}_{clip_id}"
        uploader = self._first_non_empty(
            (info or {}).get("uploader") if isinstance(info, dict) else None,
            (info or {}).get("channel") if isinstance(info, dict) else None,
            "VK",
        ) or "VK"
        thumbnail_url = self._extract_first_http_url((info or {}).get("thumbnail") if isinstance(info, dict) else None)
        thumbnail_path = None
        if thumbnail_url:
            thumbnail_path = self._generate_unique_path(f"{clip_token}_thumb", suffix=".jpg")
            if not await self._download_thumbnail(thumbnail_url, thumbnail_path, self.photo_limit):
                thumbnail_path = None

        return MediaResult(
            content_type=ContentType.VIDEO,
            source_name="VK",
            original_url=original_url,
            context=context,
            title=title,
            uploader=uploader,
            main_file_path=file_path,
            thumbnail_path=thumbnail_path,
        )
