"""
Обработчик видео-контента COUB.
"""

import aiohttp
import logging
import re
from shutil import which
from typing import Any, Dict, Optional

from src.handlers.mixins import VideoMixin

logger = logging.getLogger(__name__)


class CoubVideo(VideoMixin):
    """
    Миксин для обработки видео из COUB.
    """

    COUB_ID_PATTERN = re.compile(r"/view/([A-Za-z0-9]+)")
    COUB_API_URL_TEMPLATE = "https://coub.com/api/v2/coubs/{coub_id}.json"
    COUB_SHARE_URL_KEYS = ("share", "default")

    async def _fetch_coub_api_payload(self, coub_id: str) -> Optional[Dict[str, Any]]:
        """
        Запрашивает JSON метаданные COUB по id.
        """
        api_url = self.COUB_API_URL_TEMPLATE.format(coub_id=coub_id)
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(api_url) as response:
                    if response.status != 200:
                        logger.warning("COUB API HTTP %s for %s", response.status, api_url)
                        return None
                    payload = await response.json(content_type=None)
                    if not isinstance(payload, dict):
                        logger.warning("COUB API returned invalid payload for %s", api_url)
                        return None
                    return payload
        except Exception as exc:
            logger.warning("COUB API request failed for %s: %s", api_url, exc)
            return None

    @staticmethod
    def _extract_share_video_url(payload: Dict[str, Any]) -> Optional[str]:
        """
        Извлекает URL готового share-видео (со звуком) из payload COUB API.
        """
        file_versions = payload.get("file_versions")
        if not isinstance(file_versions, dict):
            return None
        share = file_versions.get(CoubVideo.COUB_SHARE_URL_KEYS[0])
        if not isinstance(share, dict):
            return None
        share_url = share.get(CoubVideo.COUB_SHARE_URL_KEYS[1])
        if isinstance(share_url, str) and share_url.startswith(("http://", "https://")):
            return share_url
        return None

    @staticmethod
    def _extract_uploader_from_payload(payload: Dict[str, Any]) -> str:
        """
        Возвращает имя автора из payload COUB API.
        """
        channel = payload.get("channel")
        if isinstance(channel, dict):
            channel_title = channel.get("title")
            if isinstance(channel_title, str) and channel_title.strip():
                return channel_title.strip()
        return "Unknown"

    async def _process_coub_video(
        self,
        url: str,
        context: str,
        original_url: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Скачивает COUB-видео и возвращает структуру для дальнейшей отправки.
        """
        coub_match = self.COUB_ID_PATTERN.search(url)
        coub_id = coub_match.group(1) if coub_match else self._extract_video_id(url)

        # Предпочтительный путь: собираем "чистое" видео и аудио в единый mp4.
        # Это дает звук и, как правило, вариант без watermark.
        primary_result = None
        if which("ffmpeg"):
            primary_opts = {
                "format": (
                    "html5-video-high+html5-audio-high/"
                    "html5-video-high+html5-audio-med/"
                    "html5-video-med+html5-audio-high/"
                    "bestvideo+bestaudio/best"
                ),
                "writethumbnail": True,
                "noplaylist": True,
                "merge_output_format": "mp4",
            }
            primary_result = await self._download_video(url, primary_opts, video_id=coub_id)
        else:
            logger.warning("ffmpeg is not available; COUB merge mode is skipped for %s", url)

        result = primary_result
        payload: Optional[Dict[str, Any]] = None

        # Fallback: берем share-видео напрямую из COUB API.
        # Этот путь устойчивый для звука, но может содержать watermark.
        if not result:
            payload = await self._fetch_coub_api_payload(coub_id)
            share_url = self._extract_share_video_url(payload or {})
            if share_url:
                fallback_opts = {
                    "format": "best[ext=mp4]/best",
                    "writethumbnail": False,
                    "noplaylist": True,
                }
                result = await self._download_video(
                    share_url,
                    fallback_opts,
                    video_id=f"{coub_id}_share",
                )
            else:
                logger.warning("COUB share URL is not available for %s", url)

        if not result:
            return None

        info = result["info"]
        title = info.get("title")
        uploader = info.get("uploader") or info.get("channel")

        if (not isinstance(title, str) or not title.strip()) and payload:
            payload_title = payload.get("title")
            if isinstance(payload_title, str) and payload_title.strip():
                title = payload_title.strip()

        if (not isinstance(uploader, str) or not uploader.strip()) and payload:
            uploader = self._extract_uploader_from_payload(payload)

        return {
            "type": "video",
            "source_name": "COUB",
            "file_path": result["file_path"],
            "thumbnail_path": result["thumbnail_path"],
            "title": title if isinstance(title, str) and title.strip() else "COUB Video",
            "uploader": uploader if isinstance(uploader, str) and uploader.strip() else "Unknown",
            "original_url": original_url,
            "context": context,
        }
