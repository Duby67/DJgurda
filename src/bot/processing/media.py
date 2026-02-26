import logging
import html
from aiogram import Router, F
from aiogram.types import Message
from aiogram.types.input_file import FSInputFile

from src.services.manager import ServiceManager
from src.bot.utils import split_into_blocks, get_user_link

logger = logging.getLogger(__name__)

router = Router()
service_manager = ServiceManager()

@router.message(F.text & ~F.text.startswith("/"))
async def handle_media_message(message: Message) -> None:
    text = message.text
    blocks = split_into_blocks(text, service_manager)
    if not blocks:
        return

    user_link = get_user_link(message.from_user)
    # Удаляем исходное сообщение
    try:
        await message.delete()
        logger.info("Исходное сообщение удалено")
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение: {e}")

    for idx, (url, user_context, handler) in enumerate(blocks, start=1):
        file_info = await handler.process(url, user_context)

        if file_info:
            try:
                # Формируем подпись (как у вас)
                caption_lines = []
                if user_context:
                    safe_context = html.escape(user_context)
                    caption_lines.append(safe_context)
                if handler.source_name != "Яндекс.Музыка":
                    if file_info['type'] == 'video':
                        safe_title = html.escape(file_info['title'])
                        safe_uploader = html.escape(file_info['uploader'])
                        caption_lines.append("")
                        caption_lines.append(f"🎬 {safe_title} — {safe_uploader}")

                caption_lines.append("")
                caption_lines.append(f"От ↣ {user_link}")
                caption_lines.append(f"<a href='{url}'>{handler.source_name}</a>")
                caption = "\n".join(caption_lines)

                # Отправка
                if file_info['type'] == 'video':
                    video = FSInputFile(file_info['file_path'])
                    thumb = FSInputFile(file_info['thumbnail_path']) if file_info.get('thumbnail_path') and file_info['thumbnail_path'].exists() else None
                    await message.answer_video(video=video, caption=caption, thumbnail=thumb, supports_streaming=True)
                elif file_info['type'] == 'audio':
                    audio = FSInputFile(file_info['file_path'])
                    thumb = FSInputFile(file_info['thumbnail_path']) if file_info.get('thumbnail_path') and file_info['thumbnail_path'].exists() else None
                    await message.answer_audio(audio=audio, title=file_info['title'], performer=file_info['uploader'], thumbnail=thumb, caption=caption)
                elif file_info['type'] == 'photo':
                    photo = FSInputFile(file_info['file_path'])
                    await message.answer_photo(photo=photo, caption=caption)

                logger.info(f"Блок {idx} успешно отправлен")
            except Exception as e:
                logger.exception(f"Ошибка при отправке контента для {url}")
                error_text = (f"❌ Не удалось отправить контент.\n"
                              f"{user_context}\n\n"
                              f"От ↣ {user_link}\n"
                              f"{url}")
                await message.answer(text=error_text)
            finally:
                handler.cleanup(file_info)
        else:
            error_text = (f"❌ Не удалось загрузить контент.\n\n"
                          f"{user_context}\n\n"
                          f"От ↣ {user_link}\n"
                          f"{url}")
            await message.answer(text=error_text)
            logger.info(f"Блок {idx}: ошибка загрузки")