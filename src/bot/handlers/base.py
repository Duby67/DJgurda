import re
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

class BaseHandler(ABC):
    """Абстрактный базовый класс для всех обработчиков контента."""

    @property
    @abstractmethod
    def pattern(self) -> re.Pattern:
        """Регулярное выражение для поиска ссылок данного типа."""
        pass

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Название источника."""
        pass

    @abstractmethod
    async def process(self, url: str, context: str) -> Optional[Dict[str, Any]]:
        """
        Загружает контент по ссылке.
        Возвращает словарь с полями:
        - type: 'video' или 'audio'
        - file_path: Path
        - thumbnail_path: Path или None
        - title: str
        - performer/uploader: str
        - original_url: str
        - context: str (переданный контекст)
        В случае ошибки возвращает None.
        """
        pass

    @abstractmethod
    def cleanup(self, file_info: Dict[str, Any]) -> None:
        """Удаляет временные файлы после отправки."""
        pass