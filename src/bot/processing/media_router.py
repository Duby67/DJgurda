import logging
import asyncio

from aiogram import Router, F
from aiogram.types import Message, ReplyParameters


from src.handlers.manager import ServiceManager
from src.middlewares.db import get_errors_enabled
from src.utils.url import resolve_url
from src.utils.Emoji import EMOJI_ERROR

from .link_extractor import split_into_blocks, get_user_link
from .media_processor import process_block

logger = logging.getLogger(__name__)

router = Router()
service_manager = ServiceManager()

@router.message(F.text | F.caption)
async def handle_media_message(message: Message) -> None:
    text = message.text or message.caption
    if text.startswith("/"):
        return
    
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
                    f"{EMOJI_ERROR} Неподдерживаемый источник: {resolved_url}",
                    reply_parameters=ReplyParameters(message_id=message.message_id, quote=raw_url)
                )
            continue

        tasks.append(
            process_block(
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