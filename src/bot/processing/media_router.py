import logging
import asyncio

from aiogram import Router, F
from aiogram.types import Message, ReplyParameters
from aiogram.types.input_file import FSInputFile

from src.services.manager import ServiceManager
from src.bot.commands.toggle_errors import is_error_messages_enabled
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

async def _process_single_block(
    idx: int,
    url: str,
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
            file_info = await handler.process(url, user_context)

        if not file_info:
            if is_error_messages_enabled(chat_id):
                error_text = build_error_text("Не удалось загрузить контент", url, handler)
                await message.answer(text=error_text, reply_parameters=ReplyParameters(message_id=message.message_id, quote=url))
            logger.info(f"Блок {idx}: ошибка загрузки file_info")
            return False

        caption = build_caption(user_context, file_info, user_link, url, handler)

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
            return True
        
        except Exception as e:
            if is_error_messages_enabled(chat_id):
                error_text = build_error_text("Не удалось отправить контент", url, handler)
                await message.answer(text=error_text, reply_parameters=ReplyParameters(message_id=message.message_id), quote=url)
            logger.exception(f"Ошибка при отправке контента для {url}")
            return False
        
        finally:
            if file_info:
                handler.cleanup(file_info)
                
    except Exception as e:
        if is_error_messages_enabled(chat_id):
            error_text = build_error_text("Внутренняя ошибка при обработке ссылки", url, handler)
            await message.answer(text=error_text, reply_parameters=ReplyParameters(message_id=message.message_id, quote=url))
        logger.exception(f"Необработанная ошибка при обработке блока {idx}: {e}")
        return False

@router.message(F.text & ~F.text.startswith("/"))
async def handle_media_message(message: Message) -> None:
    text = message.text
    blocks = split_into_blocks(text, service_manager)
    if not blocks:
        logger.debug("Сообщение не содержит поддерживаемых ссылок")
        return

    user_link = get_user_link(message.from_user)

    tasks = [
        _process_single_block(idx, url, context, handler, user_link, message)
        for idx, (url, context, handler) in enumerate(blocks, start=1)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    success_count = 0
    for res in results:
        if res is True:
            success_count += 1
        elif isinstance(res, Exception):
            logger.error(f"Необработанное исключение в задаче: {res}")
    if success_count > 0:
        try:
            await message.delete()
            logger.info("Исходное сообщение удалено")
        except Exception as e:
            logger.warning(f"Не удалось удалить сообщение: {e}")
    else:
        logger.info("Все блоки завершились ошибкой, исходное сообщение сохранено")