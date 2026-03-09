"""Модуль `base`."""
import re
import logging

from pathlib import Path
from abc import ABC, abstractmethod
from typing import Any, Dict, Iterable, Optional

from src.handlers.contracts import HandlerOutput

logger = logging.getLogger(__name__)


class BaseHandler(ABC):
    """Класс `BaseHandler`."""
    @property
    @abstractmethod
    def pattern(self) -> re.Pattern:
        """Функция `pattern`."""
        pass

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Функция `source_name`."""
        pass

    @abstractmethod
    async def process(self, url: str, context: str, resolved_url: Optional[str] = None) -> Optional[HandlerOutput]:
        """Функция `process`."""
        pass

    def _collect_paths_for_cleanup(self, file_info: Dict[str, Any]) -> Iterable[Path]:
        """Собирает все временные пути, которые могут быть в результате обработчика."""
        for key in ("file_path", "thumbnail_path"):
            path = file_info.get(key)
            if isinstance(path, Path):
                yield path

        for media_item in file_info.get("files", []):
            media_path = media_item.get("file_path") if isinstance(media_item, dict) else None
            if isinstance(media_path, Path):
                yield media_path

        audio_info = file_info.get("audio")
        if isinstance(audio_info, dict):
            audio_path = audio_info.get("file_path")
            if isinstance(audio_path, Path):
                yield audio_path
            audio_thumbnail_path = audio_info.get("thumbnail_path")
            if isinstance(audio_thumbnail_path, Path):
                yield audio_thumbnail_path

        for audio_item in file_info.get("audios", []):
            if not isinstance(audio_item, dict):
                continue
            audio_path = audio_item.get("file_path")
            if isinstance(audio_path, Path):
                yield audio_path
            audio_thumbnail_path = audio_item.get("thumbnail_path")
            if isinstance(audio_thumbnail_path, Path):
                yield audio_thumbnail_path

    def cleanup(self, file_info: Dict[str, Any]) -> None:
        """Функция `cleanup`."""
        for path in set(self._collect_paths_for_cleanup(file_info)):
            try:
                path.unlink(missing_ok=True)
            except Exception as exc:
                logger.error("Failed to delete %s: %s", path, exc)
