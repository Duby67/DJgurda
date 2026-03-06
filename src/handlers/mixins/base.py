"""
Базовый миксин для обработки медиа.

Содержит общие методы и конфигурацию для всех медиа-миксинов.
"""

import uuid
import random
import asyncio
import logging

from pathlib import Path

from src.config import (
    PROJECT_TEMP_DIR, 
    VIDEO_SIZE_LIMIT, 
    PHOTO_SIZE_LIMIT, 
    AUDIO_SIZE_LIMIT
)

logger = logging.getLogger(__name__)

class BaseMixin:
    """
    Базовый класс для миксинов обработки медиа.
    
    Предоставляет общие методы для генерации путей, задержек и извлечения идентификаторов.
    """
    
    # Лимиты размеров файлов (в байтах)
    video_limit = VIDEO_SIZE_LIMIT
    photo_limit = PHOTO_SIZE_LIMIT
    audio_limit = AUDIO_SIZE_LIMIT

    def __init__(self, *args, **kwargs):
        """
        Инициализирует миксин, создавая временную директорию для класса.
        """
        super().__init__(*args, **kwargs)
        self.temp_dir = PROJECT_TEMP_DIR / self.__class__.__name__
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Временная директория для {self.__class__.__name__}: {self.temp_dir}")

    def _generate_unique_path(self, identifier: str, suffix: str = "") -> Path:
        """
        Генерирует уникальный путь для временного файла.
        
        Args:
            identifier: Базовый идентификатор (например, ID видео)
            suffix: Расширение файла (например, ".mp4")
            
        Returns:
            Path: Уникальный путь к файлу
        """
        unique_id = f"{identifier}_{uuid.uuid4().hex[:8]}"
        return self.temp_dir / f"{unique_id}{suffix}"

    def _extract_video_id(self, url: str) -> str:
        """
        Извлекает идентификатор видео из URL.
        
        Args:
            url: URL видео
            
        Returns:
            str: Идентификатор видео
        """
        parts = url.rstrip('/').split('/')
        return parts[-1].split('?')[0]

    async def _random_delay(self, min_sec: float = 1, max_sec: float = 3) -> None:
        """
        Случайная задержка между запросами для избежания блокировок.
        
        Args:
            min_sec: Минимальная задержка в секундах
            max_sec: Максимальная задержка в секундах
        """
        delay = random.uniform(min_sec, max_sec)
        logger.debug(f"Ожидание {delay:.2f} секунд")
        await asyncio.sleep(delay)
