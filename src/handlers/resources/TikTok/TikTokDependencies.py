"""
Явные зависимости TikTok-контура.

Модуль убирает скрытую зависимость от MRO и предоставляет
компоненты, которые передаются в процессоры как explicit dependencies.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Protocol

from src.config import TIKTOK_COOKIES, TIKTOK_COOKIES_ENABLED
from src.handlers.infrastructure import (
    DelayPolicyService,
    HttpFileService,
    RuntimePathService,
    YtdlpMediaGroupService,
    YtdlpOptionBuilder,
    YtdlpVideoService,
)
from src.utils.cookies import CookieFile


class TikTokOptionsProviderProtocol(Protocol):
    """Контракт поставщика yt-dlp cookie/options для TikTok."""

    def build_ytdlp_opts(self) -> dict[str, str]:
        """Возвращает опции cookies для yt-dlp."""


class TikTokMediaGatewayProtocol(Protocol):
    """Контракт low-level операций для TikTok-процессоров."""

    photo_limit: int
    audio_limit: int

    async def random_delay(self, *, min_sec: float = 1, max_sec: float = 3) -> None:
        """Выполняет случайную задержку между сетевыми запросами."""

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
        """Скачивает все элементы медиа-группы."""

    async def download_photo(
        self,
        image_url: str,
        dest_path: Path,
        *,
        size_limit: Optional[int] = None,
    ) -> bool:
        """Скачивает изображение."""

    async def download_audio(
        self,
        url: str,
        dest_path: Path,
        *,
        size_limit: Optional[int] = None,
    ) -> bool:
        """Скачивает аудио."""

    async def download_thumbnail(
        self,
        url: str,
        dest_path: Path,
        *,
        size_limit: Optional[int] = None,
    ) -> bool:
        """Скачивает миниатюру/обложку."""


class TikTokCookieOptionsProvider:
    """Поставщик cookie/options для TikTok на основе `CookieFile`."""

    def __init__(self, runtime_dir: Path) -> None:
        self._tiktok_cookies = CookieFile(
            provider_key="tiktok",
            provider_name="TikTok",
            enabled=TIKTOK_COOKIES_ENABLED,
            cookie_path=TIKTOK_COOKIES,
            path_env_name="TIKTOK_COOKIES_PATH",
            runtime_dir=runtime_dir,
        )

    def build_ytdlp_opts(self) -> dict[str, str]:
        """Возвращает cookiefile-опции для yt-dlp."""
        return self._tiktok_cookies.build_ytdlp_opts()


class TikTokMediaGateway:
    """Реализация low-level операций TikTok через composition-сервисы."""

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
        self._http_service = HttpFileService(delay_policy=self._delay_policy)
        self.photo_limit = self._http_service.photo_limit
        self.audio_limit = self._http_service.audio_limit

    async def random_delay(self, *, min_sec: float = 1, max_sec: float = 3) -> None:
        """Выполняет случайную задержку между сетевыми запросами."""
        await self._delay_policy.random_delay(min_sec=min_sec, max_sec=max_sec)

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
        """Скачивает все элементы медиа-группы."""
        return await self._media_group_service.download_media_group(
            url,
            ydl_opts,
            group_id=group_id,
            size_limit=size_limit,
        )

    async def download_photo(
        self,
        image_url: str,
        dest_path: Path,
        *,
        size_limit: Optional[int] = None,
    ) -> bool:
        """Скачивает изображение."""
        return await self._http_service.download_photo(image_url, dest_path, size_limit=size_limit)

    async def download_audio(
        self,
        url: str,
        dest_path: Path,
        *,
        size_limit: Optional[int] = None,
    ) -> bool:
        """Скачивает аудио."""
        return await self._http_service.download_audio(url, dest_path, size_limit=size_limit)

    async def download_thumbnail(
        self,
        url: str,
        dest_path: Path,
        *,
        size_limit: Optional[int] = None,
    ) -> bool:
        """Скачивает миниатюру/обложку."""
        return await self._http_service.download_thumbnail(url, dest_path, size_limit=size_limit)
