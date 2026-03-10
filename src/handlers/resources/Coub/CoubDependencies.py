"""
Явные зависимости Coub-контура.

Модуль убирает скрытую зависимость от MRO и предоставляет
компоненты, которые передаются в процессоры как explicit dependencies.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Protocol

from src.handlers.infrastructure import (
    DelayPolicyService,
    RuntimePathService,
    YtdlpOptionBuilder,
    YtdlpVideoService,
)


class CoubOptionsProviderProtocol(Protocol):
    """Контракт поставщика yt-dlp options для Coub."""

    def build_ytdlp_opts(self) -> dict[str, Any]:
        """Возвращает дополнительные опции для yt-dlp."""


class CoubMediaGatewayProtocol(Protocol):
    """Контракт low-level операций для Coub-процессоров."""

    video_limit: int

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


class CoubYtdlpOptionsProvider:
    """Поставщик дополнительных yt-dlp опций для Coub."""

    def build_ytdlp_opts(self) -> dict[str, Any]:
        """Возвращает дополнительные опции для yt-dlp."""
        return {}


class CoubMediaGateway:
    """Реализация low-level операций Coub через composition-сервисы."""

    def __init__(self, runtime_dir: Path) -> None:
        self._runtime_paths = RuntimePathService(runtime_dir=runtime_dir)
        self._delay_policy = DelayPolicyService()
        self._option_builder = YtdlpOptionBuilder(scope=self.__class__.__name__)
        self._video_service = YtdlpVideoService(
            runtime_paths=self._runtime_paths,
            delay_policy=self._delay_policy,
            option_builder=self._option_builder,
        )
        self.video_limit = self._video_service.video_limit

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
