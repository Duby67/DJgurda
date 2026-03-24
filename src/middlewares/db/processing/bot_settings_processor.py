"""
Процессор для работы с настройками бота в чатах.

Содержит функции для управления состоянием бота, показом ошибок и уведомлениями.
"""

import logging
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace

from sqlalchemy import select

from src.middlewares.db.core import AsyncSessionLocal
from src.middlewares.db.models.bot_settings import BotSettings

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ChatSettingsSnapshot:
    """Снимок настроек чата для bounded per-update cache."""

    bot_enabled: bool = True
    errors_enabled: bool = False
    notifications_enabled: bool = False


_SETTINGS_CACHE: ContextVar[dict[int, ChatSettingsSnapshot] | None] = ContextVar(
    "bot_settings_cache",
    default=None,
)


class SettingsReadError(RuntimeError):
    """Ошибка чтения settings из БД."""

    def __init__(self, message: str, *, chat_id: int | None = None, column: str | None = None) -> None:
        super().__init__(message)
        self.chat_id = chat_id
        self.column = column


def _build_snapshot(settings: BotSettings | None) -> ChatSettingsSnapshot:
    """Нормализует ORM-запись в typed settings snapshot."""
    if settings is None:
        return ChatSettingsSnapshot()

    return ChatSettingsSnapshot(
        bot_enabled=settings.bot_enabled,
        errors_enabled=settings.errors_enabled,
        notifications_enabled=settings.notifications_enabled,
    )


def _get_cache_store() -> dict[int, ChatSettingsSnapshot] | None:
    """Возвращает текущий scoped cache store, если он активен."""
    return _SETTINGS_CACHE.get()


def _get_cached_snapshot(chat_id: int) -> ChatSettingsSnapshot | None:
    """Читает cached settings snapshot для чата из текущего scope."""
    store = _get_cache_store()
    if store is None:
        return None
    return store.get(chat_id)


def _store_snapshot(chat_id: int, snapshot: ChatSettingsSnapshot) -> None:
    """Сохраняет snapshot в текущий scoped cache."""
    store = _get_cache_store()
    if store is not None:
        store[chat_id] = snapshot


def _update_cached_snapshot(chat_id: int, column: str, value: bool) -> None:
    """Обновляет cached snapshot после write в рамках текущего scope."""
    store = _get_cache_store()
    if store is None or chat_id not in store:
        return
    store[chat_id] = replace(store[chat_id], **{column: value})


@asynccontextmanager
async def settings_cache_scope():
    """
    Открывает bounded cache scope на время одного update flow.
    """
    existing_store = _get_cache_store()
    if existing_store is not None:
        yield existing_store
        return

    token = _SETTINGS_CACHE.set({})
    try:
        yield _SETTINGS_CACHE.get()
    finally:
        _SETTINGS_CACHE.reset(token)


async def _get_settings_snapshot(chat_id: int, requested_column: str) -> ChatSettingsSnapshot:
    """Читает все settings чата одним fetch и использует scoped cache, если он активен."""
    cached = _get_cached_snapshot(chat_id)
    if cached is not None:
        return cached

    try:
        async with AsyncSessionLocal() as session:
            settings = await session.get(BotSettings, chat_id)
            snapshot = _build_snapshot(settings)
            if settings is None:
                logger.debug("settings snapshot for chat %s: record not found", chat_id)
            _store_snapshot(chat_id, snapshot)
            return snapshot
    except Exception as exc:
        logger.exception("Error in _get_settings_snapshot(%s) for chat %s", requested_column, chat_id)
        raise SettingsReadError(
            f"Failed to read {requested_column} for chat {chat_id}",
            chat_id=chat_id,
            column=requested_column,
        ) from exc


async def _get_setting(chat_id: int, column: str, default: bool) -> bool:
    """
    Получает значение настройки для чата.
    
    Аргументы:
        chat_id: ID чата
        column: Название колонки (bot_enabled, errors_enabled, notifications_enabled)
        default: Значение по умолчанию если запись не найдена
        
    Возвращает:
        Значение настройки или значение по умолчанию

    Raises:
        SettingsReadError: если БД недоступна или чтение settings сломалось.
    """
    snapshot = await _get_settings_snapshot(chat_id, column)
    return getattr(snapshot, column, default)


async def _set_setting(chat_id: int, column: str, value: bool) -> None:
    """
    Устанавливает значение настройки для чата.
    
    Аргументы:
        chat_id: ID чата
        column: Название колонки
        value: Новое значение
        
    Raises:
        Exception: При ошибках работы с БД
    """
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                settings = await session.get(BotSettings, chat_id)
                if settings is None:
                    settings = BotSettings(chat_id=chat_id)
                    setattr(settings, column, value)
                    session.add(settings)
                    logger.info(f"Created record for chat {chat_id} with {column}={value}")
                else:
                    setattr(settings, column, value)
                    logger.info(f"Updated {column} for chat {chat_id}: {value}")
        _update_cached_snapshot(chat_id, column, value)
    except Exception:
        logger.exception(f"Error in _set_setting({column}) for chat {chat_id}")
        raise


async def get_chats_with_notifications_enabled() -> list[int]:
    """
    Получает список чатов с включенными уведомлениями.
    
    Возвращает:
        Список ID чатов с уведомлениями

    Raises:
        SettingsReadError: если список чатов не удалось прочитать из БД.
    """
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(BotSettings.chat_id).where(BotSettings.notifications_enabled.is_(True))
            )
            return [row[0] for row in result.all()]
    except Exception as exc:
        logger.exception("Failed to get list of chats with notifications")
        raise SettingsReadError(
            "Failed to get list of chats with notifications",
            column="notifications_enabled",
        ) from exc


# Функции для управления состоянием бота
async def set_bot_enabled(chat_id: int, enabled: bool) -> None:
    """Включает или выключает бота в чате."""
    await _set_setting(chat_id, "bot_enabled", enabled)

async def set_errors_enabled(chat_id: int, enabled: bool) -> None:
    """Включает или выключает показ ошибок в чате."""
    await _set_setting(chat_id, "errors_enabled", enabled)

async def set_notifications_enabled(chat_id: int, enabled: bool) -> None:
    """Включает или выключает уведомления в чате."""
    await _set_setting(chat_id, "notifications_enabled", enabled)

async def get_bot_enabled(chat_id: int) -> bool:
    """Проверяет, включен ли бот в чате."""
    return await _get_setting(chat_id, "bot_enabled", True)

async def get_errors_enabled(chat_id: int) -> bool:
    """Проверяет, включен ли показ ошибок в чате."""
    return await _get_setting(chat_id, "errors_enabled", False)

async def get_notifications_enabled(chat_id: int) -> bool:
    """Проверяет, включены ли уведомления в чате."""
    return await _get_setting(chat_id, "notifications_enabled", False)
