"""Менеджер runtime-обработчиков поверх декларативного registry."""

from __future__ import annotations

import logging
from typing import Optional

from src.handlers.base import BaseHandler
from src.handlers.registry import HandlerRegistry, RuntimeHandlerEntry, get_default_handler_registry

logger = logging.getLogger(__name__)


def get_active_handler_names() -> tuple[str, ...]:
    """Возвращает имена активных runtime handler-классов."""
    return get_default_handler_registry().get_runtime_handler_names()


class ServiceManager:
    """Thin-wrapper над `HandlerRegistry` для поиска handler-а по URL."""

    def __init__(self, registry: HandlerRegistry | None = None) -> None:
        self.registry = registry or get_default_handler_registry()
        self._entries: list[RuntimeHandlerEntry] = self.registry.create_runtime_entries()
        self.handlers: list[BaseHandler] = [entry.handler for entry in self._entries]
        logger.info("Registered handlers: %s", len(self.handlers))

    def get_handler(self, url: str) -> Optional[BaseHandler]:
        """Находит обработчик, поддерживающий данный URL."""
        for entry in self._entries:
            if entry.descriptor.pattern.search(url):
                logger.debug("Handler found for %s: %s", url, entry.descriptor.source_name)
                return entry.handler

        logger.debug("No handler found for URL: %s", url)
        return None
