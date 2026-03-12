"""Модуль `media_router`."""
import logging
import asyncio
from enum import StrEnum
from typing import Awaitable, Optional

from aiogram import Router, F
from aiogram.types import Message, ReplyParameters

from src.handlers.manager import ServiceManager, get_active_handler_names
from src.middlewares.db import get_errors_enabled
from src.utils.url import resolve_url
from src.utils.Emoji import EMOJI_ERROR

from .link_extractor import split_into_blocks, get_user_link
from .media_processor import process_block

logger = logging.getLogger(__name__)

router = Router()
service_manager: Optional[ServiceManager] = None


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
    for idx, (raw_url, context) in enumerate(blocks, start=1):
        resolved_url = await resolve_url(raw_url)
        # Сначала пытаемся подобрать handler по исходному URL пользователя.
        # Это снижает риск потери классификации на anti-bot redirect-страницах.
        handler = manager.get_handler(raw_url)
        if not handler:
            handler = manager.get_handler(resolved_url)
        if not handler:
            logger.warning(f"No handler found for resolved URL: {resolved_url}")
            if await get_errors_enabled(message.chat.id):
                await message.answer(
                    (
                        f"{EMOJI_ERROR} Ссылка не обработана.\n"
                        "Причина: неподдерживаемый источник или формат ссылки.\n"
                        f"Поддерживаемые источники: {supported_sources}."
                    ),
                    reply_parameters=ReplyParameters(message_id=message.message_id, quote=raw_url)
                )
            block_outcomes[idx] = BlockOutcome.UNSUPPORTED
            continue

        pending_blocks.append(
            (
                idx,
                raw_url,
                process_block(
                    idx,
                    raw_url,
                    resolved_url,
                    context,
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
