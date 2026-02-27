import re
import uuid
import asyncio
import logging
import random
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Dict, Any

from src.config import PHOTO_SIZE_LIMIT
from src.config import VIDEO_SIZE_LIMIT

logger = logging.getLogger(__name__)

class BaseHandler(ABC):
    TEMP_DIR: Path = None
    video_limit = VIDEO_SIZE_LIMIT
    photo_limit = PHOTO_SIZE_LIMIT

    @property
    @abstractmethod
    def pattern(self) -> re.Pattern:
        pass

    @property
    @abstractmethod
    def source_name(self) -> str:
        pass

    @abstractmethod
    async def process(self, url: str, context: str) -> Optional[Dict[str, Any]]:
        pass

    def _generate_unique_path(self, identifier: str, suffix: str = "") -> Path:
        unique_id = f"{identifier}_{uuid.uuid4().hex[:8]}"
        return self.TEMP_DIR / f"{unique_id}{suffix}"

    def _extract_video_id(self, url: str) -> str:
        parts = url.rstrip('/').split('/')
        return parts[-1].split('?')[0]

    async def _random_delay(self):
        delay = random.uniform(1, 3)
        logger.info(f"Ожидание {delay:.2f} секунд")
        await asyncio.sleep(delay)

    def cleanup(self, file_info: Dict[str, Any]) -> None:
        for key in ['file_path', 'thumbnail_path']:
            path = file_info.get(key)
            if path and isinstance(path, Path):
                try:
                    path.unlink(missing_ok=True)
                except Exception as e:
                    logger.error(f"Ошибка удаления {path}: {e}")