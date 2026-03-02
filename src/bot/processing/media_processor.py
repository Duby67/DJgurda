import re
import logging
import asyncio

from typing import List, Tuple
from aiogram.types import User

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

DOWNLOAD_SEMAPHORE = asyncio.Semaphore(3)
URL_PATTERN = re.compile(r'https?://\S+')

async def process_block(
    idx: int,
    raw_url: str,
    resolved_url: str,
    user_context: str,
    handler,
    user_link: str,
    message: Message
) -> bool:
    """Обрабатывает один блок: загружает и отправляет медиа."""
    file_info = None
    chat_id = message.chat.id
    try:
        async with DOWNLOAD_SEMAPHORE:
            file_info = await handler.process(raw_url, user_context, resolved_url=resolved_url)

        if not file_info:
            if await get_errors_enabled(chat_id):
                error_text = build_error_text("Не удалось загрузить контент", raw_url, handler)
                await message.answer(text=error_text, reply_parameters=ReplyParameters(message_id=message.message_id, quote=raw_url))
            logger.info(f"Блок {idx}: ошибка загрузки file_info")
            return False
        
        caption = build_caption(user_context, file_info, user_link, raw_url, handler)

        try:
            if file_info['type'] == 'video':
                video = FSInputFile(file_info['file_path'])
                thumb = FSInputFile(file_info['thumbnail_path']) if file_info.get('thumbnail_path') and file_info['thumbnail_path'].exists() else None
                await message.answer_video(
                    video=video,
                    caption=caption,
                    thumbnail=thumb,
                    supports_streaming=True
                )                
            elif file_info['type'] == 'audio':
                audio = FSInputFile(file_info['file_path'])
                thumb = FSInputFile(file_info['thumbnail_path']) if file_info.get('thumbnail_path') and file_info['thumbnail_path'].exists() else None
                await message.answer_audio(
                    audio=audio,
                    title=file_info['title'],
                    performer=file_info['uploader'],
                    thumbnail=thumb,
                    caption=caption
                )
            elif file_info['type'] == 'photo':
                photo = FSInputFile(file_info['file_path'])
                await message.answer_photo(photo=photo, caption=caption)

            logger.info(f"Блок {idx} успешно отправлен")
            await update_stats(message.chat.id, message.from_user.id, handler.source_name)
            return True
        
        except Exception as e:
            if await get_errors_enabled(chat_id):
                error_text = build_error_text("Не удалось отправить контент", raw_url, handler)
                await message.answer(text=error_text, reply_parameters=ReplyParameters(message_id=message.message_id, quote=raw_url))
            logger.exception(f"Ошибка при отправке контента для {raw_url}")
            return False
        
        finally:
            if file_info:
                handler.cleanup(file_info)
                
    except Exception as e:
        if await get_errors_enabled(chat_id):
            error_text = build_error_text("Внутренняя ошибка при обработке ссылки", raw_url, handler)
            await message.answer(text=error_text, reply_parameters=ReplyParameters(message_id=message.message_id, quote=raw_url))
        logger.exception(f"Необработанная ошибка при обработке блока {idx}: {e}")
        return False
    
def split_into_blocks(text: str) -> List[Tuple[str, str]]:
    urls = URL_PATTERN.findall(text)
    if not urls:
        return []
    parts = re.split(URL_PATTERN, text)
    
    blocks = []
    for i, url in enumerate(urls):
        context_before = parts[i].strip()
        if i == len(urls) - 1:
            context_after = parts[-1].strip()
            if context_after:
                if context_before:
                    context = context_before + '\n' + context_after
                else:
                    context = context_after
            else:
                context = context_before
        else:
            context = context_before

        blocks.append((url, context))

    return blocks