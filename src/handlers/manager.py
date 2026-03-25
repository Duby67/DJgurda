"""Менеджер runtime-обработчиков поверх декларативного registry."""

from __future__ import annotations

import logging
from typing import Optional, Sequence

from src.handlers.base import BaseHandler
from src.handlers.registry import (
    HandlerRegistry,
    RuntimeHandlerEntry,
    get_default_handler_registry,
    get_handler_registry_with_non_runtime_sources,
)

logger = logging.getLogger(__name__)


def get_active_handler_names() -> tuple[str, ...]:
    """Возвращает имена активных runtime handler-классов."""
    return get_default_handler_registry().get_runtime_handler_names()


class ServiceManager:
    """Thin-wrapper над `HandlerRegistry` для поиска handler-а по URL."""

    def __init__(
        self,
        registry: HandlerRegistry | None = None,
        *,
        non_runtime_sources: Sequence[str] | None = None,
    ) -> None:
        if registry is not None:
            self.registry = registry
        elif non_runtime_sources:
            self.registry = get_handler_registry_with_non_runtime_sources(non_runtime_sources)
        else:
            self.registry = get_default_handler_registry()
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

    def resolve_handler(
        self,
        raw_url: str,
        resolved_url: str | None = None,
    ) -> Optional[BaseHandler]:
        """
        Ищет handler для runtime-flow, сохраняя ownership lookup policy внутри manager.

        Сначала пробует исходный URL пользователя, затем fallback на resolved URL.
        """
        handler = self.get_handler(raw_url)
        if handler is not None:
            return handler

        if resolved_url and resolved_url != raw_url:
            return self.get_handler(resolved_url)

        return None
