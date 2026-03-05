import logging
import aiohttp
import aiofiles

from pathlib import Path

from .base import BaseMixin

logger = logging.getLogger(__name__)

class AudioMixin(BaseMixin):
    async def _download_file(self, url: str, dest_path: Path) -> bool:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.error(f"Ошибка скачивания {url}: HTTP {response.status}")
                        return False
                    async with aiofiles.open(dest_path, 'wb') as f:
                        await f.write(await response.read())
            return True
        except Exception as e:
            logger.exception(f"Ошибка при скачивании {url}: {e}")
            return False

    async def _download_audio(
        self,
        url: str,
        dest_path: Path,
        size_limit: int = None
    ) -> bool:
        if size_limit is None:
            size_limit = self.audio_limit

        await self._random_delay()

        success = await self._download_file(url, dest_path)
        if not success:
            return False

        file_size = dest_path.stat().st_size
        if file_size > size_limit:
            logger.warning(f"Аудио слишком большое ({file_size} байт). Удаляем.")
            dest_path.unlink(missing_ok=True)
            return False
        return True

    async def _download_thumbnail(self, url: str, dest_path: Path, size_limit: int = None) -> bool:
        if size_limit is None:
            size_limit = self.photo_limit

        await self._random_delay()

        success = await self._download_file(url, dest_path)
        if not success:
            return False

        file_size = dest_path.stat().st_size
        if file_size > size_limit:
            logger.warning(f"Обложка слишком большая ({file_size} байт). Удаляем.")
            dest_path.unlink(missing_ok=True)
            return False
        return True