"""
Явные зависимости YouTube-контура.

Модуль убирает скрытую зависимость от MRO и предоставляет
компоненты, которые можно передавать в процессоры как explicit dependencies.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any, Optional, Protocol

from src.config import YOUTUBE_COOKIES, YOUTUBE_COOKIES_ENABLED
from src.handlers.mixins import MetadataMixin, PhotoMixin, VideoMixin
from src.utils.cookies import CookieFile


class YouTubeOptionsProviderProtocol(Protocol):
    """Контракт поставщика yt-dlp cookie/options для YouTube."""

    def build_ytdlp_opts(self) -> dict[str, str]:
        """Возвращает опции cookies для yt-dlp."""


class YouTubeMediaGatewayProtocol(Protocol):
    """Контракт low-level операций для YouTube-процессоров."""

    photo_limit: int

    def extract_video_id(self, url: str) -> str:
        """Извлекает video id из URL."""

    async def download_video(
        self,
        url: str,
        ydl_opts: dict[str, Any],
        *,
        video_id: str,
    ) -> Optional[dict[str, Any]]:
        """Скачивает видео через yt-dlp."""

    async def extract_metadata(
        self,
        url: str,
        ydl_opts: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Извлекает метаданные без скачивания контента."""

    def pick_thumbnail_url(
        self,
        info: dict[str, Any],
        *,
        candidate_keys: Iterable[str],
    ) -> Optional[str]:
        """Выбирает лучший thumbnail URL из payload."""

    def generate_unique_path(self, identifier: str, *, suffix: str = "") -> Path:
        """Генерирует уникальный runtime-путь."""

    async def download_photo(
        self,
        image_url: str,
        dest_path: Path,
        *,
        size_limit: Optional[int] = None,
    ) -> bool:
        """Скачивает изображение."""


class YouTubeCookieOptionsProvider:
    """Поставщик cookie/options для YouTube на основе `CookieFile`."""

    def __init__(self, runtime_dir: Path) -> None:
        self._youtube_cookies = CookieFile(
            provider_key="youtube",
            provider_name="YouTube",
            enabled=YOUTUBE_COOKIES_ENABLED,
            cookie_path=YOUTUBE_COOKIES,
            path_env_name="YOUTUBE_COOKIES_PATH",
            runtime_dir=runtime_dir,
        )

    def build_ytdlp_opts(self) -> dict[str, str]:
        """Возвращает cookiefile-опции для yt-dlp."""
        return self._youtube_cookies.build_ytdlp_opts()


class YouTubeMediaGateway(VideoMixin, MetadataMixin, PhotoMixin):
    """
    Реализация low-level операций YouTube через существующие mixins.

    Mixins используются только как внутренний механизм этого gateway-объекта,
    а не как публичный runtime-контракт handler-а.
    """

    def __init__(self, runtime_dir: Path) -> None:
        super().__init__()
        self.temp_dir = runtime_dir
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def extract_video_id(self, url: str) -> str:
        """Извлекает video id из URL."""
        return self._extract_video_id(url)

    async def download_video(
        self,
        url: str,
        ydl_opts: dict[str, Any],
        *,
        video_id: str,
    ) -> Optional[dict[str, Any]]:
        """Скачивает видео через yt-dlp."""
        return await self._download_video(url, ydl_opts, video_id=video_id)

    async def extract_metadata(
        self,
        url: str,
        ydl_opts: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Извлекает метаданные через yt-dlp."""
        return await self._extract_metadata(url, ydl_opts)

    def pick_thumbnail_url(
        self,
        info: dict[str, Any],
        *,
        candidate_keys: Iterable[str],
    ) -> Optional[str]:
        """Возвращает URL миниатюры из metadata payload."""
        return self._pick_thumbnail_url(info, candidate_keys=candidate_keys)

    def generate_unique_path(self, identifier: str, *, suffix: str = "") -> Path:
        """Генерирует уникальный runtime-путь."""
        return self._generate_unique_path(identifier, suffix=suffix)

    async def download_photo(
        self,
        image_url: str,
        dest_path: Path,
        *,
        size_limit: Optional[int] = None,
    ) -> bool:
        """Скачивает изображение."""
        return await self._download_photo(image_url, dest_path, size_limit=size_limit)