"""
Миксин для обработки изображений.
"""

import logging
import aiohttp
import aiofiles

from pathlib import Path

from .base import BaseMixin

logger = logging.getLogger(__name__)

class PhotoMixin(BaseMixin):
    """
    Миксин для загрузки изображений через aiohttp.
    """
    
    async def _download_photo(
        self,
        image_url: str,
        dest_path: Path,
        size_limit: int = None
    ) -> bool:
        """
        Скачивает изображение по URL.
        
        Args:
            image_url: URL изображения
            dest_path: Путь для сохранения
            size_limit: Лимит размера файла в байтах
            
        Returns:
            bool: Успешно ли скачано изображение
        """
        if size_limit is None:
            size_limit = self.photo_limit

        await self._random_delay()

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url, headers=headers, timeout=10) as response:
                    if response.status != 200:
                        logger.error(f"Ошибка скачивания {image_url}: HTTP {response.status}")
                        return False
                    
                    # Сохраняем изображение
                    async with aiofiles.open(dest_path, 'wb') as f:
                        await f.write(await response.read())
                        
        except Exception as e:
            logger.exception(f"Ошибка при скачивании изображения: {e}")
            return False

        # Проверяем размер файла
        file_size = dest_path.stat().st_size
        if file_size > size_limit:
            logger.warning(f"Фото слишком большое ({file_size} байт). Удаляем.")
            dest_path.unlink(missing_ok=True)
            return False
            
        return True
