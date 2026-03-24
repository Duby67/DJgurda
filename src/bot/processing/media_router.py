"""Модуль `media_router`."""
import logging
import asyncio
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Awaitable, Optional

from aiogram import Router, F
from aiogram.types import Message, ReplyParameters

from src.handlers.manager import ServiceManager, get_active_handler_names
from src.middlewares.db import get_errors_enabled
from src.middlewares.db.processing.bot_settings_processor import SettingsReadError
from src.utils.url import resolve_url
from src.utils.Emoji import EMOJI_ERROR

from .link_extractor import split_into_blocks, get_user_link
from .media_processor import process_block

logger = logging.getLogger(__name__)

router = Router()
service_manager: Optional[ServiceManager] = None
MAX_CONCURRENT_URL_RESOLVES = 4


@dataclass(slots=True)
class PreparedBlock:
    """Результат preflight-подготовки блока до запуска process_block."""

    idx: int
    raw_url: str
    resolved_url: str
    context: str
    handler: Any | None


async def _get_errors_enabled(chat_id: int) -> bool:
    """Получает флаг ошибок, явно фиксируя деградацию чтения настроек."""
    try:
        return await get_errors_enabled(chat_id)
    except SettingsReadError:
        logger.warning(
            "Error settings unavailable for chat %s; suppressing error reply",
            chat_id,
            exc_info=True,
        )
        return False


class BlockOutcome(StrEnum):
    """Итоговый исход обработки одного link-block."""

    SUCCESS = "success"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


def _get_service_manager() -> ServiceManager:
    """Ленивая инициализация ServiceManager после старта приложения."""
    global service_manager
    if service_manager is None:
        service_manager = ServiceManager()
    return service_manager


async def _prepare_block(
    idx: int,
    raw_url: str,
    context: str,
    manager: ServiceManager,
    semaphore: asyncio.Semaphore,
) -> PreparedBlock:
    """Готовит routing-данные для одного блока с bounded resolve concurrency."""
    async with semaphore:
        try:
            resolved_url = await resolve_url(raw_url)
        except Exception:
            logger.warning(
                "Failed to resolve URL for block %s (%s); using raw URL fallback",
                idx,
                raw_url,
                exc_info=True,
            )
            resolved_url = raw_url

    handler = manager.resolve_handler(raw_url, resolved_url)

    return PreparedBlock(
        idx=idx,
        raw_url=raw_url,
        resolved_url=resolved_url,
        context=context,
        handler=handler,
    )


async def _prepare_blocks_for_routing(
    blocks: list[tuple[str, str]],
    manager: ServiceManager,
) -> list[PreparedBlock]:
    """Готовит multi-link batch до process_block, сохраняя исходный порядок."""
    if not blocks:
        return []

    semaphore = asyncio.Semaphore(min(MAX_CONCURRENT_URL_RESOLVES, len(blocks)))
    return await asyncio.gather(
        *(
            _prepare_block(idx, raw_url, context, manager, semaphore)
            for idx, (raw_url, context) in enumerate(blocks, start=1)
        )
    )


@router.message(F.text | F.caption)
async def handle_media_message(message: Message) -> None:
    """Функция `handle_media_message`."""
    text = message.text or message.caption
    if not text:
        return

    if text.startswith("/"):
        return
    
    blocks = split_into_blocks(text)
    if not blocks:
        logger.debug("Message does not contain links")
        return

    if not message.from_user:
        logger.debug("Message without from_user skipped")
        return

    user_link = get_user_link(message.from_user)

    pending_blocks: list[tuple[int, str, Awaitable[bool]]] = []
    block_outcomes: dict[int, BlockOutcome] = {}
    manager = _get_service_manager()
    supported_sources = ", ".join(get_active_handler_names())
    prepared_blocks = await _prepare_blocks_for_routing(blocks, manager)
    for prepared in prepared_blocks:
        # Сначала пытаемся подобрать handler по исходному URL пользователя.
        # Это снижает риск потери классификации на anti-bot redirect-страницах.
        handler = prepared.handler
        if not handler:
            logger.warning("No handler found for resolved URL: %s", prepared.resolved_url)
            if await _get_errors_enabled(message.chat.id):
                await message.answer(
                    (
                        f"{EMOJI_ERROR} Ссылка не обработана.\n"
                        "Причина: неподдерживаемый источник или формат ссылки.\n"
                        f"Поддерживаемые источники: {supported_sources}."
                    ),
                    reply_parameters=ReplyParameters(message_id=message.message_id, quote=prepared.raw_url)
                )
            block_outcomes[prepared.idx] = BlockOutcome.UNSUPPORTED
            continue

        pending_blocks.append(
            (
                prepared.idx,
                prepared.raw_url,
                process_block(
                    prepared.idx,
                    prepared.raw_url,
                    prepared.resolved_url,
                    prepared.context,
                    handler,
                    user_link,
                    message,
                ),
            )
        )

    if pending_blocks:
        results = await asyncio.gather(
            *(task for _, _, task in pending_blocks),
            return_exceptions=True,
        )
        for (idx, raw_url, _), result in zip(pending_blocks, results):
            if result is True:
                block_outcomes[idx] = BlockOutcome.SUCCESS
                continue

            block_outcomes[idx] = BlockOutcome.FAILED
            if isinstance(result, Exception):
                logger.error("Unhandled exception in block %s (%s): %s", idx, raw_url, result)

    if len(block_outcomes) != len(blocks):
        logger.warning(
            "Block outcomes mismatch: outcomes=%s blocks=%s",
            len(block_outcomes),
            len(blocks),
        )
        return

    if all(outcome == BlockOutcome.SUCCESS for outcome in block_outcomes.values()):
        try:
            await message.delete()
            logger.info("Original message deleted")
        except Exception as exc:
            logger.warning("Failed to delete message: %s", exc)
    else:
        logger.info("Original message retained due to non-success block outcomes")
