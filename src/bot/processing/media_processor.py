import logging
import asyncio

from aiogram.types import Message, ReplyParameters
from aiogram.types.input_file import FSInputFile

from src.utils.messages import build_caption, build_error
from src.middlewares.db import get_errors_enabled, update_stats
from .link_extractor import split_into_blocks, get_user_link

logger = logging.getLogger(__name__)

DOWNLOAD_SEMAPHORE = asyncio.Semaphore(3)

async def process_block(
    idx: int,
    raw_url: str,
    resolved_url: str,
    user_context: str,
    handler,
    user_link: str,
    message: Message
) -> bool:
    file_info = None
    chat_id = message.chat.id
    try:
        async with DOWNLOAD_SEMAPHORE:
            file_info = await handler.process(raw_url, user_context, resolved_url=resolved_url)

        if not file_info:
            if await get_errors_enabled(chat_id):
                error_text = build_error("Не удалось загрузить контент", raw_url, handler)
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
                error_text = build_error("Не удалось отправить контент", raw_url, handler)
                await message.answer(text=error_text, reply_parameters=ReplyParameters(message_id=message.message_id, quote=raw_url))
            logger.exception(f"Ошибка при отправке контента для {raw_url}")
            return False
        
        finally:
            if file_info:
                handler.cleanup(file_info)
                
    except Exception as e:
        if await get_errors_enabled(chat_id):
            error_text = build_error("Внутренняя ошибка при обработке ссылки", raw_url, handler)
            await message.answer(text=error_text, reply_parameters=ReplyParameters(message_id=message.message_id, quote=raw_url))
        logger.exception(f"Необработанная ошибка при обработке блока {idx}: {e}")
        return False