"""
Миксин для извлечения метаданных через yt-dlp без скачивания медиа.
"""

import asyncio
import logging
from typing import Any, Dict, Iterable, Optional

import yt_dlp

from .base import BaseMixin
from src.utils.cookies import cleanup_runtime_cookiefile

logger = logging.getLogger(__name__)


class MetadataMixin(BaseMixin):
    """
    Миксин с общими утилитами для получения и разбора метаданных.
    """

    async def _extract_metadata(self, url: str, ydl_opts: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Извлекает метаданные URL через yt-dlp без загрузки файла.
        """
        default_opts = {
            "skip_download": True,
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "geo_bypass": True,
        }
        merged_opts = self._build_ytdlp_opts(default_opts, ydl_opts)
        cookiefile_path = merged_opts.get("cookiefile")

        await self._random_delay()

        try:
            with yt_dlp.YoutubeDL(merged_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, url, download=False)
            if not isinstance(info, dict):
                logger.warning("Metadata extraction returned invalid payload for %s", url)
                return None
            return info
        except Exception as exc:
            logger.exception("Failed to extract metadata for %s: %s", url, exc)
            return None
        finally:
            cleanup_runtime_cookiefile(cookiefile_path)

    @staticmethod
    def _extract_first_http_url(value: Any) -> Optional[str]:
        """
        Пытается извлечь первый HTTP(S) URL из произвольной структуры.
        """
        if isinstance(value, str):
            return value if value.startswith(("http://", "https://")) else None

        if isinstance(value, (list, tuple)):
            for item in value:
                found = MetadataMixin._extract_first_http_url(item)
                if found:
                    return found
            return None

        if isinstance(value, dict):
            for nested_value in value.values():
                found = MetadataMixin._extract_first_http_url(nested_value)
                if found:
                    return found
            return None

        return None

    def _pick_thumbnail_url(
        self,
        info: Dict[str, Any],
        candidate_keys: Iterable[str],
    ) -> Optional[str]:
        """
        Возвращает первый валидный URL миниатюры из списка ключей.
        """
        for key in candidate_keys:
            if key not in info:
                continue
            found = self._extract_first_http_url(info.get(key))
            if found:
                return found
        return None
