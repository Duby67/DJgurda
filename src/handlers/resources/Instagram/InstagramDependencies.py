"""
Явные зависимости Instagram-контура.

Модуль убирает скрытую зависимость от MRO и предоставляет
компоненты, которые передаются в процессоры как explicit dependencies.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Optional, Protocol

from src.config import INSTAGRAM_COOKIES, INSTAGRAM_COOKIES_ENABLED
from src.handlers.infrastructure import (
    DelayPolicyService,
    HttpFileService,
    RuntimePathService,
    YtdlpMediaGroupService,
    YtdlpMetadataService,
    YtdlpOptionBuilder,
    YtdlpVideoService,
)
from src.utils.cookies import CookieFile


class InstagramOptionsProviderProtocol(Protocol):
    """Контракт поставщика yt-dlp cookie/options для Instagram."""

    def build_ytdlp_opts(self) -> dict[str, str]:
        """Возвращает опции cookies для yt-dlp."""


class InstagramMediaGatewayProtocol(Protocol):
    """Контракт low-level операций для Instagram-процессоров."""

    video_limit: int
    photo_limit: int

    def extract_video_id(self, url: str) -> str:
        """Извлекает video id из URL."""

    def generate_unique_path(self, identifier: str, *, suffix: str = "") -> Path:
        """Генерирует уникальный runtime-путь."""

    async def download_video(
        self,
        url: str,
        ydl_opts: dict[str, Any],
        *,
        video_id: str,
    ) -> Optional[dict[str, Any]]:
        """Скачивает видео через yt-dlp."""

    async def download_media_group(
        self,
        url: str,
        ydl_opts: dict[str, Any],
        *,
        group_id: str,
        size_limit: Optional[int] = None,
    ) -> Optional[list[dict[str, Any]]]:
        """Скачивает элементы медиа-группы."""

    async def extract_metadata(
        self,
        url: str,
        ydl_opts: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Извлекает метаданные без скачивания медиа."""

    def pick_thumbnail_url(
        self,
        info: dict[str, Any],
        *,
        candidate_keys: Iterable[str],
    ) -> Optional[str]:
        """Возвращает URL миниатюры из metadata payload."""

    async def download_photo(
        self,
        image_url: str,
        dest_path: Path,
        *,
        size_limit: Optional[int] = None,
    ) -> bool:
        """Скачивает изображение."""


class InstagramCookieOptionsProvider:
    """Поставщик cookie/options для Instagram на основе `CookieFile`."""

    def __init__(self, runtime_dir: Path) -> None:
        self._instagram_cookies = CookieFile(
            provider_key="instagram",
            provider_name="Instagram",
            enabled=INSTAGRAM_COOKIES_ENABLED,
            cookie_path=INSTAGRAM_COOKIES,
            path_env_name="INSTAGRAM_COOKIES_PATH",
            runtime_dir=runtime_dir,
        )

    def build_ytdlp_opts(self) -> dict[str, str]:
        """Возвращает cookiefile-опции для yt-dlp."""
        return self._instagram_cookies.build_ytdlp_opts()


class InstagramMediaGateway:
    """Реализация low-level операций Instagram через composition-сервисы."""

    def __init__(self, runtime_dir: Path) -> None:
        self._runtime_paths = RuntimePathService(runtime_dir=runtime_dir)
        self._delay_policy = DelayPolicyService()
        self._option_builder = YtdlpOptionBuilder(scope=self.__class__.__name__)
        self._video_service = YtdlpVideoService(
            runtime_paths=self._runtime_paths,
            delay_policy=self._delay_policy,
            option_builder=self._option_builder,
        )
        self._media_group_service = YtdlpMediaGroupService(
            runtime_paths=self._runtime_paths,
            delay_policy=self._delay_policy,
            option_builder=self._option_builder,
            default_size_limit=self._video_service.video_limit,
        )
        self._metadata_service = YtdlpMetadataService(
            delay_policy=self._delay_policy,
            option_builder=self._option_builder,
        )
        self._http_service = HttpFileService(delay_policy=self._delay_policy)
        self.video_limit = self._video_service.video_limit
        self.photo_limit = self._http_service.photo_limit

    def extract_video_id(self, url: str) -> str:
        """Извлекает video id из URL."""
        return self._runtime_paths.extract_video_id(url)

    def generate_unique_path(self, identifier: str, *, suffix: str = "") -> Path:
        """Генерирует уникальный runtime-путь."""
        return self._runtime_paths.generate_unique_path(identifier, suffix=suffix)

    async def download_video(
        self,
        url: str,
        ydl_opts: dict[str, Any],
        *,
        video_id: str,
    ) -> Optional[dict[str, Any]]:
        """Скачивает видео через yt-dlp."""
        return await self._video_service.download_video(url, ydl_opts, video_id=video_id)

    async def download_media_group(
        self,
        url: str,
        ydl_opts: dict[str, Any],
        *,
        group_id: str,
        size_limit: Optional[int] = None,
    ) -> Optional[list[dict[str, Any]]]:
        """Скачивает элементы медиа-группы."""
        return await self._media_group_service.download_media_group(
            url,
            ydl_opts,
            group_id=group_id,
            size_limit=size_limit,
        )

    async def extract_metadata(
        self,
        url: str,
        ydl_opts: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Извлекает метаданные через yt-dlp."""
        return await self._metadata_service.extract_metadata(url, ydl_opts)

    def pick_thumbnail_url(
        self,
        info: dict[str, Any],
        *,
        candidate_keys: Iterable[str],
    ) -> Optional[str]:
        """Возвращает URL миниатюры из metadata payload."""
        return self._metadata_service.pick_thumbnail_url(info, candidate_keys=candidate_keys)

    async def download_photo(
        self,
        image_url: str,
        dest_path: Path,
        *,
        size_limit: Optional[int] = None,
    ) -> bool:
        """Скачивает изображение."""
        return await self._http_service.download_photo(image_url, dest_path, size_limit=size_limit)
