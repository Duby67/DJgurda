"""Декларативный runtime registry обработчиков."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Pattern, Sequence

from src.handlers.base import BaseHandler
from src.handlers.contracts import ContentType
from src.handlers.resources.Coub import CoubHandler
from src.handlers.resources.Instagram import InstagramHandler
from src.handlers.resources.TikTok import TikTokHandler
from src.handlers.resources.YouTube import YouTubeHandler

HandlerFactory = Callable[[], BaseHandler]

# Явная фиксация source-статусов вне stable runtime-контура.
_NON_RUNTIME_SOURCE_STATUSES: dict[str, str] = {
    "YandexMusic": "legacy",
    "VK": "in_development",
}


@dataclass(frozen=True, slots=True)
class HandlerDescriptor:
    """
    Декларативное описание runtime-обработчика.

    Поля:
    - `pattern`: паттерн распознавания URL;
    - `priority`: приоритет выбора (большее значение = выше приоритет);
    - `feature_flags`: runtime-флаги для поэтапного включения;
    - `factory`: фабрика создания handler-экземпляра;
    - `source_name`: имя источника;
    - `supported_content_types`: поддерживаемые `ContentType`.
    """

    source_name: str
    pattern: Pattern[str]
    priority: int
    feature_flags: tuple[str, ...]
    factory: HandlerFactory
    supported_content_types: tuple[ContentType, ...]


@dataclass(frozen=True, slots=True)
class RuntimeHandlerEntry:
    """Связка descriptor + runtime-экземпляр handler-а."""

    descriptor: HandlerDescriptor
    handler: BaseHandler


class HandlerRegistry:
    """Registry descriptor-объектов и фабрик обработчиков."""

    def __init__(self, descriptors: Sequence[HandlerDescriptor]) -> None:
        self._descriptors = tuple(
            sorted(
                descriptors,
                key=lambda item: item.priority,
                reverse=True,
            )
        )

    @property
    def descriptors(self) -> tuple[HandlerDescriptor, ...]:
        """Возвращает descriptors в порядке runtime-приоритета."""
        return self._descriptors

    def create_runtime_entries(self) -> list[RuntimeHandlerEntry]:
        """Создает runtime-экземпляры обработчиков по фабрикам descriptors."""
        entries: list[RuntimeHandlerEntry] = []
        for descriptor in self._descriptors:
            handler = descriptor.factory()
            entries.append(RuntimeHandlerEntry(descriptor=descriptor, handler=handler))
        return entries

    def get_runtime_handler_names(self) -> tuple[str, ...]:
        """Возвращает имена runtime handler-классов для подготовки temp storage."""
        names: list[str] = []
        for descriptor in self._descriptors:
            factory = descriptor.factory
            name = getattr(factory, "__name__", descriptor.source_name)
            names.append(name)
        return tuple(names)


def _default_descriptors() -> tuple[HandlerDescriptor, ...]:
    """
    Возвращает дефолтный runtime-набор descriptor-объектов.

    Важно: новые handlers добавляются декларативно через этот список.

    В intentionally excluded non-runtime зоне:
    - `YandexMusic` остается в статусе legacy;
    - `VK` остается в статусе in_development.
    """
    return (
        HandlerDescriptor(
            source_name="TikTok",
            pattern=TikTokHandler.PATTERN,
            priority=100,
            feature_flags=("runtime_enabled",),
            factory=TikTokHandler,
            supported_content_types=(
                ContentType.VIDEO,
                ContentType.PHOTO,
                ContentType.MEDIA_GROUP,
                ContentType.PROFILE,
            ),
        ),
        HandlerDescriptor(
            source_name="YouTube",
            pattern=YouTubeHandler.PATTERN,
            priority=90,
            feature_flags=("runtime_enabled",),
            factory=YouTubeHandler,
            supported_content_types=(
                ContentType.SHORTS,
                ContentType.CHANNEL,
            ),
        ),
        HandlerDescriptor(
            source_name="Instagram",
            pattern=InstagramHandler.PATTERN,
            priority=80,
            feature_flags=("runtime_enabled",),
            factory=InstagramHandler,
            supported_content_types=(
                ContentType.REELS,
                ContentType.MEDIA_GROUP,
                ContentType.STORIES,
                ContentType.PROFILE,
            ),
        ),
        HandlerDescriptor(
            source_name="COUB",
            pattern=CoubHandler.PATTERN,
            priority=70,
            feature_flags=("runtime_enabled",),
            factory=CoubHandler,
            supported_content_types=(ContentType.VIDEO,),
        ),
    )


_DEFAULT_HANDLER_REGISTRY: HandlerRegistry | None = None


def get_default_handler_registry() -> HandlerRegistry:
    """Возвращает singleton-реестр runtime handlers."""
    global _DEFAULT_HANDLER_REGISTRY
    if _DEFAULT_HANDLER_REGISTRY is None:
        _DEFAULT_HANDLER_REGISTRY = HandlerRegistry(_default_descriptors())
    return _DEFAULT_HANDLER_REGISTRY


def get_non_runtime_source_statuses() -> dict[str, str]:
    """Возвращает статусы источников, исключенных из stable runtime."""
    return dict(_NON_RUNTIME_SOURCE_STATUSES)
