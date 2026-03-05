import asyncio
import logging
import requests
from pathlib import Path
from typing import Optional

from .base import BaseMixin

logger = logging.getLogger(__name__)

class PhotoMixin(BaseMixin):
    async def _download_photo(
        self,
        image_url: str,
        dest_path: Path,
        size_limit: int = None
    ) -> bool:
        if size_limit is None:
            size_limit = self.photo_limit

        await self._random_delay()

        def sync_download():
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            try:
                response = requests.get(image_url, headers=headers, timeout=10)
                if response.status_code != 200:
                    logger.error(f"Ошибка скачивания {image_url}: {response.status_code}")
                    return False
                with open(dest_path, 'wb') as f:
                    f.write(response.content)
                return True
            except Exception as e:
                logger.exception(f"Ошибка при скачивании изображения: {e}")
                return False

        success = await asyncio.to_thread(sync_download)
        if success:
            file_size = dest_path.stat().st_size
            if file_size > size_limit:
                logger.warning(f"Фото слишком большое ({file_size} байт). Удаляем.")
                dest_path.unlink(missing_ok=True)
                return False
        return success