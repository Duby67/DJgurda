import re
import logging

from pathlib import Path
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class BaseHandler(ABC):
    @property
    @abstractmethod
    def pattern(self) -> re.Pattern:
        pass

    @property
    @abstractmethod
    def source_name(self) -> str:
        pass

    @abstractmethod
    async def process(self, url: str, context: str, resolved_url: Optional[str] = None) -> Optional[Dict[str, Any]]:
        pass

    def cleanup(self, file_info: Dict[str, Any]) -> None:
        for key in ['file_path', 'thumbnail_path']:
            path = file_info.get(key)
            if path and isinstance(path, Path):
                try:
                    path.unlink(missing_ok=True)
                except Exception as e:
                    logger.error(f"Ошибка удаления {path}: {e}")