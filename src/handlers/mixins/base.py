"""
Базовый миксин для обработки медиа.

Содержит общие методы и конфигурацию для всех медиа-миксинов.
"""

import uuid
import random
import asyncio
import logging

from pathlib import Path
from typing import Any, Dict, Optional

from src.config import (
    PROJECT_TEMP_DIR, 
    VIDEO_SIZE_LIMIT, 
    PHOTO_SIZE_LIMIT, 
    AUDIO_SIZE_LIMIT
)
from src.utils.cookies import build_ytdlp_cookiefile_opt

logger = logging.getLogger(__name__)


class _YtdlpQuietLogger:
    """
    Тихий logger для yt-dlp, перенаправляющий технические сообщения в debug-уровень.
    """

    def __init__(self, scope: str) -> None:
        self._scope = scope

    def debug(self, message: str) -> None:
        logger.debug("%s yt-dlp: %s", self._scope, message)

    def info(self, message: str) -> None:
        logger.debug("%s yt-dlp: %s", self._scope, message)

    def warning(self, message: str) -> None:
        logger.debug("%s yt-dlp warning: %s", self._scope, message)

    def error(self, message: str) -> None:
        logger.debug("%s yt-dlp error: %s", self._scope, message)


class BaseMixin:
    """
    Базовый класс для миксинов обработки медиа.
    
    Предоставляет общие методы для генерации путей, задержек и извлечения идентификаторов.
    """
    
    # Лимиты размеров файлов (в байтах)
    video_limit: int = VIDEO_SIZE_LIMIT
    photo_limit: int = PHOTO_SIZE_LIMIT
    audio_limit: int = AUDIO_SIZE_LIMIT

    def __init__(self, *args: object, **kwargs: object) -> None:
        """
        Инициализирует миксин, создавая временную директорию для класса.
        """
        super().__init__(*args, **kwargs)
        self.temp_dir = PROJECT_TEMP_DIR / self.__class__.__name__
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Temporary directory for {self.__class__.__name__}: {self.temp_dir}")

    def _generate_unique_path(self, identifier: str, suffix: str = "") -> Path:
        """
        Генерирует уникальный путь для временного файла.
        
        Аргументы:
            identifier: Базовый идентификатор (например, ID видео)
            suffix: Расширение файла (например, ".mp4")
            
        Возвращает:
            Path: Уникальный путь к файлу
        """
        # Директория может быть очищена runtime-обслуживанием между запросами.
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        unique_id = f"{identifier}_{uuid.uuid4().hex[:8]}"
        return self.temp_dir / f"{unique_id}{suffix}"

    def _extract_video_id(self, url: str) -> str:
        """
        Извлекает идентификатор видео из URL.
        
        Аргументы:
            url: URL видео
            
        Возвращает:
            str: Идентификатор видео
        """
        parts = url.rstrip('/').split('/')
        return parts[-1].split('?')[0]

    def _build_ytdlp_opts(
        self,
        default_opts: Dict[str, Any],
        ydl_opts: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Объединяет опции yt-dlp и автоматически подключает тихий logger.
        """
        merged_opts: Dict[str, Any] = dict(default_opts)
        if ydl_opts:
            merged_opts.update(ydl_opts)

        merged_opts.setdefault("quiet", True)
        merged_opts.setdefault("no_warnings", True)
        merged_opts.setdefault("logger", _YtdlpQuietLogger(self.__class__.__name__))
        return merged_opts

    def _build_ytdlp_cookiefile_opts(
        self,
        *,
        provider_key: str,
        provider_name: str,
        enabled: bool,
        cookie_path: Optional[Path],
        path_env_name: str,
    ) -> Dict[str, str]:
        """
        Возвращает безопасные `cookiefile`-опции для yt-dlp.

        Общая логика вынесена в `src.utils.cookies`, чтобы все наследники
        `BaseMixin` использовали единый контракт работы с cookies.
        """
        return build_ytdlp_cookiefile_opt(
            provider_key=provider_key,
            provider_name=provider_name,
            enabled=enabled,
            cookie_path=cookie_path,
            path_env_name=path_env_name,
            log=logger,
            runtime_dir=self.temp_dir,
        )

    async def _random_delay(self, min_sec: float = 1, max_sec: float = 3) -> None:
        """
        Случайная задержка между запросами для избежания блокировок.
        
        Аргументы:
            min_sec: Минимальная задержка в секундах
            max_sec: Максимальная задержка в секундах
        """
        delay = random.uniform(min_sec, max_sec)
        logger.debug(f"Waiting {delay:.2f} seconds")
        await asyncio.sleep(delay)
