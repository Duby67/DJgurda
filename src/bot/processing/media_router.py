import logging
import asyncio

from aiogram import Router, F
from aiogram.types import Message, ReplyParameters
from aiogram.types.input_file import FSInputFile

from src.utils.url import resolve_url
from src.handlers.manager import ServiceManager
from src.middlewares.db import get_errors_enabled, update_stats
from src.bot.processing.text_utils import (
    split_into_blocks,
    get_user_link,
    build_caption,
    build_error_text
)

logger = logging.getLogger(__name__)

router = Router()
service_manager = ServiceManager()
DOWNLOAD_SEMAPHORE = asyncio.Semaphore(3)


@router.message(F.text & ~F.text.startswith("/"))
async def handle_media_message(message: Message) -> None:
    text = message.text
    blocks = split_into_blocks(text)
    if not blocks:
        logger.debug("Сообщение не содержит ссылок")
        return

    user_link = get_user_link(message.from_user)

    tasks = []
    for idx, (raw_url, context) in enumerate(blocks, start=1):
        
        resolved_url = await resolve_url(raw_url)
        handler = service_manager.get_handler(resolved_url)
        if not handler:
            logger.warning(f"Не найден обработчик для разрешённого URL: {resolved_url}")
            if await get_errors_enabled(message.chat.id):
                await message.answer(
                    f"❌ Неподдерживаемый источник: {resolved_url}",
                    reply_parameters=ReplyParameters(message_id=message.message_id, quote=raw_url)
                )
            continue

        tasks.append(
            _process_single_block(
                idx,
                raw_url,
                resolved_url,
                context,
                handler,
                user_link,
                message
            )
        )

    if not tasks:
        return

    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    success_count = 0
    for res in results:
        if res is True:
            success_count += 1
        elif isinstance(res, Exception):
            logger.error(f"Необработанное исключение в задаче: {res}")
    if success_count == len(blocks):
        try:
            await message.delete()
            logger.info("Исходное сообщение удалено")
        except Exception as e:
            logger.warning(f"Не удалось удалить сообщение: {e}")
    else:
        logger.info("Не все блоки завершились успешно")