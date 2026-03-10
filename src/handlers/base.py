"""Модуль `base`."""
import re

from abc import ABC, abstractmethod
from typing import Optional

from src.handlers.contracts import MediaResult


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
    async def process(self, url: str, context: str, resolved_url: Optional[str] = None) -> Optional[MediaResult]:
        """Функция `process`."""
        pass
