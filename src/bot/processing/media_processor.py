"""Модуль `media_processor`."""

import asyncio
import logging
from typing import Any

from aiogram.types import Message, ReplyParameters

from src.bot.processing.senders import DEFAULT_SENDER_REGISTRY
from src.handlers.adapters import adapt_handler_output
from src.handlers.contracts import MediaResult
from src.middlewares.db import get_errors_enabled, update_stats
from src.utils.messages import build_caption, build_error

logger = logging.getLogger(__name__)

# Ограничение параллельных загрузок
DOWNLOAD_SEMAPHORE = asyncio.Semaphore(3)


def _cleanup_media_result(media_result: MediaResult | None) -> None:
    """Удаляет временные файлы по typed-контракту результата."""
    if media_result is None:
        return

    for path in media_result.iter_cleanup_paths():
        try:
            path.unlink(missing_ok=True)
        except Exception as exc:
            logger.error("Failed to delete %s: %s", path, exc)


async def process_block(
    idx: int,
    raw_url: str,
    resolved_url: str,
    user_context: str,
    handler: Any,
    user_link: str,
    message: Message,
) -> bool:
    """
    Обрабатывает один блок (ссылка + контекст).

    Возвращает:
        True если обработка успешна, иначе False.
    """
    media_result: MediaResult | None = None
    chat_id = message.chat.id

    try:
        async with DOWNLOAD_SEMAPHORE:
            handler_output = await handler.process(raw_url, user_context, resolved_url=resolved_url)

        if not handler_output:
            if await get_errors_enabled(chat_id):
                error_text = build_error("Не удалось загрузить контент", raw_url, handler)
                await message.answer(
                    text=error_text,
                    reply_parameters=ReplyParameters(
                        message_id=message.message_id,
                        quote=raw_url,
                    ),
                )
            logger.info("Block %s: failed to load handler output", idx)
            return False

        media_result = adapt_handler_output(
            handler_output,
            fallback_source_name=handler.source_name,
            default_original_url=raw_url,
            default_context=user_context,
        )

        caption = build_caption(
            user_context=user_context,
            media_result=media_result,
            user_link=user_link,
            url=raw_url,
            handler=handler,
        )

        try:
            await DEFAULT_SENDER_REGISTRY.send(
                message=message,
                result=media_result,
                caption=caption,
            )
            logger.info("Block %s sent successfully", idx)
            if message.from_user:
                await update_stats(message.chat.id, message.from_user.id, handler.source_name)
            return True
        except Exception:
            if await get_errors_enabled(chat_id):
                error_text = build_error("Не удалось отправить контент", raw_url, handler)
                await message.answer(
                    text=error_text,
                    reply_parameters=ReplyParameters(
                        message_id=message.message_id,
                        quote=raw_url,
                    ),
                )
            logger.exception("Failed to send content for %s", raw_url)
            return False
        finally:
            _cleanup_media_result(media_result)

    except Exception as exc:
        if await get_errors_enabled(chat_id):
            error_text = build_error("Внутренняя ошибка при обработке ссылки", raw_url, handler)
            await message.answer(
                text=error_text,
                reply_parameters=ReplyParameters(
                    message_id=message.message_id,
                    quote=raw_url,
                ),
            )
        logger.exception("Unhandled error while processing block %s: %s", idx, exc)
        return False
