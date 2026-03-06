"""
Миксин для обработки аудио файлов.
"""

import logging
import aiohttp
import aiofiles

from pathlib import Path
from typing import Optional

from .base import BaseMixin

logger = logging.getLogger(__name__)


class AudioMixin(BaseMixin):
    """
    Миксин для загрузки аудио файлов и миниатюр.
    """
    
    async def _download_file(self, url: str, dest_path: Path) -> bool:
        """
        Базовый метод для загрузки файла по URL.
        
        Args:
            url: URL файла
            dest_path: Путь для сохранения
            
        Returns:
            bool: Успешно ли скачан файл
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.error(f"Ошибка скачивания {url}: HTTP {response.status}")
                        return False
                    
                    async with aiofiles.open(dest_path, 'wb') as f:
                        await f.write(await response.read())
            return True
        except Exception as exc:
            logger.exception("Ошибка при скачивании %s: %s", url, exc)
            return False

    async def _download_audio(
        self,
        url: str,
        dest_path: Path,
        size_limit: Optional[int] = None
    ) -> bool:
        """
        Скачивает аудио файл по URL.
        
        Args:
            url: URL аудио файла
            dest_path: Путь для сохранения
            size_limit: Лимит размера файла в байтах
            
        Returns:
            bool: Успешно ли скачан аудио файл
        """
        if size_limit is None:
            size_limit = self.audio_limit

        await self._random_delay()

        success = await self._download_file(url, dest_path)
        if not success:
            return False

        # Проверяем размер файла
        file_size = dest_path.stat().st_size
        if file_size > size_limit:
            logger.warning(f"Аудио слишком большое ({file_size} байт). Удаляем.")
            dest_path.unlink(missing_ok=True)
            return False
            
        return True

    async def _download_thumbnail(
        self, 
        url: str, 
        dest_path: Path, 
        size_limit: Optional[int] = None
    ) -> bool:
        """
        Скачивает миниатюру/обложку по URL.
        
        Args:
            url: URL миниатюры
            dest_path: Путь для сохранения
            size_limit: Лимит размера файла в байтах
            
        Returns:
            bool: Успешно ли скачана миниатюра
        """
        if size_limit is None:
            size_limit = self.photo_limit

        await self._random_delay()

        success = await self._download_file(url, dest_path)
        if not success:
            return False

        # Проверяем размер файла
        file_size = dest_path.stat().st_size
        if file_size > size_limit:
            logger.warning(f"Обложка слишком большая ({file_size} байт). Удаляем.")
            dest_path.unlink(missing_ok=True)
            return False
            
        return True
