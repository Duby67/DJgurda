import logging
import asyncio

from typing import Any

from aiogram import types
from aiogram.types import Message, ReplyParameters
from aiogram.types.input_file import FSInputFile

from src.utils.messages import build_caption, build_error
from src.middlewares.db import get_errors_enabled, update_stats

logger = logging.getLogger(__name__)

# Ограничение параллельных загрузок
DOWNLOAD_SEMAPHORE = asyncio.Semaphore(3)

async def process_block(
    idx: int,
    raw_url: str,
    resolved_url: str,
    user_context: str,
    handler: Any,
    user_link: str,
    message: Message
) -> bool:
    """
    Обрабатывает один блок (ссылка + контекст).
    
    Args:
        idx: Порядковый номер блока
        raw_url: Исходный URL
        resolved_url: Разрешенный URL
        user_context: Контекст пользователя
        handler: Обработчик для данного типа контента
        user_link: HTML-ссылка на пользователя
        message: Исходное сообщение
        
    Returns:
        True если обработка успешна, иначе False
    """
    file_info = None
    chat_id = message.chat.id
    
    try:
        # Ограничиваем параллельные загрузки
        async with DOWNLOAD_SEMAPHORE:
            file_info = await handler.process(raw_url, user_context, resolved_url=resolved_url)

        if not file_info:
            if await get_errors_enabled(chat_id):
                error_text = build_error("Не удалось загрузить контент", raw_url, handler)
                await message.answer(
                    text=error_text, 
                    reply_parameters=ReplyParameters(
                        message_id=message.message_id, 
                        quote=raw_url
                    )
                )
            logger.info(f"Блок {idx}: ошибка загрузки file_info")
            return False
        
        # Строим подпись для медиа
        caption = build_caption(user_context, file_info, user_link, raw_url, handler)

        try:
            # Обрабатываем разные типы медиа
            if file_info['type'] == 'video':
                video = FSInputFile(file_info['file_path'])
                thumb = (
                    FSInputFile(file_info['thumbnail_path']) 
                    if file_info.get('thumbnail_path') and file_info['thumbnail_path'].exists() 
                    else None
                )
                await message.answer_video(
                    video=video,
                    caption=caption,
                    thumbnail=thumb,
                    supports_streaming=True
                )                
            elif file_info['type'] == 'audio':
                audio = FSInputFile(file_info['file_path'])
                thumb = (
                    FSInputFile(file_info['thumbnail_path']) 
                    if file_info.get('thumbnail_path') and file_info['thumbnail_path'].exists() 
                    else None
                )
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
                
            elif file_info['type'] == 'media_group':
                # Отправляем группу медиа
                media = []
                for f in file_info['files']:
                    if f['type'] == 'photo':
                        media.append(types.InputMediaPhoto(media=FSInputFile(f['file_path'])))
                
                if media:
                    # Добавляем подпись к последнему медиа в группе
                    media[-1].caption = caption
                    await message.answer_media_group(media=media)

                # Отдельно отправляем аудио, если есть
                if 'audio' in file_info:
                    audio = FSInputFile(file_info['audio']['file_path'])
                    await message.answer_audio(
                        audio=audio,
                        title=file_info['audio']['title'],
                        performer=file_info['audio']['performer'],
                        caption=None
                    )
                
            elif file_info['type'] == 'profile':
                if file_info['file_path'] and file_info['file_path'].exists():
                    photo = FSInputFile(file_info['file_path'])
                    await message.answer_photo(photo=photo, caption=file_info['caption_text'])
                else:
                    await message.answer(file_info['caption_text'])

            logger.info(f"Блок {idx} успешно отправлен")
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
                        quote=raw_url
                    )
                )
            logger.exception(f"Ошибка при отправке контента для {raw_url}")
            return False
        
        finally:
            # Очищаем временные файлы
            if file_info:
                handler.cleanup(file_info)
                
    except Exception as exc:
        if await get_errors_enabled(chat_id):
            error_text = build_error("Внутренняя ошибка при обработке ссылки", raw_url, handler)
            await message.answer(
                text=error_text, 
                reply_parameters=ReplyParameters(
                    message_id=message.message_id, 
                    quote=raw_url
                )
            )
        logger.exception("Необработанная ошибка при обработке блока %s: %s", idx, exc)
        return False
