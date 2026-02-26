import html
import asyncio
import logging

from zoneinfo import ZoneInfo
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.types import FSInputFile
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties

from src.config import ADMIN_ID, BOT_TOKEN
from src.utils.logger import setup_logging
from src.bot.processing import split_into_blocks, get_user_link

from src.bot.handlers.services.base import BaseHandler

from src.services.TikTok import TikTokHandler
from src.services.YouTube import YouTubeShortsHandler
from src.services.Instagram import InstagramReelsHandler
from src.services.YandexMusic import YandexMusicHandler

setup_logging()
logger = logging.getLogger(__name__)

# Регистрируем все обработчики
handlers: list[BaseHandler] = [
    TikTokHandler(),
    YandexMusicHandler(),
    YouTubeShortsHandler(),
    InstagramReelsHandler(),
]

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

start_time: datetime | None = None

async def on_startup() -> None:
    """Действия при старте бота."""
    global start_time
    utc_time = datetime.now(timezone.utc)
    moscow_tz = ZoneInfo("Europe/Moscow")
    start_time = utc_time.astimezone(moscow_tz)
    logger.info("Бот запущен")
    try:
        await bot.send_message(chat_id=ADMIN_ID, text="✅ Бот успешно запущен и готов к работе!")
    except Exception as e:
        logger.error(f"Не удалось отправить уведомление о запуске: {e}")

async def on_shutdown() -> None:
    """Действия при остановке бота."""
    logger.info("Бот останавливается...")
    try:
        await bot.send_message(chat_id=ADMIN_ID, text="⚠️ Бот выключается...")
    except Exception as e:
        logger.error(f"Не удалось отправить уведомление о выключении: {e}")




        
@dp.message(F.text & ~F.text.startswith("/"))
async def handle_message(message: types.Message) -> None:
    text = message.text
    blocks = split_into_blocks(text, handlers)
    if not blocks:
        return

    user_link = get_user_link(message.from_user)
    chat_id = message.chat.id

    # Удаляем исходное сообщение
    try:
        await message.delete()
        logger.info("Исходное сообщение удалено")
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение: {e}")

    # Обрабатываем каждый блок
    for idx, (url, user_context, handler) in enumerate(blocks, start=1):
        file_info = await handler.process(url, user_context)

        if file_info:
            # Успешная загрузка
            try:
                # Формируем подпись
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

                # Отправка в зависимости от типа
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
                        performer=file_info['performer'],
                        thumbnail=thumb,
                        caption=caption
                    )
                elif file_info['type'] == 'photo':
                    photo = FSInputFile(file_info['file_path'])
                    await message.answer_photo(
                        photo=photo,
                        caption=caption
                    )

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
            # Ошибка загрузки контента
            error_text = (f"❌ Не удалось загрузить контент.\n\n"
                          f"{user_context}\n\n"
                          f"От ↣ {user_link}\n"
                          f"{url}")
            await message.answer(text=error_text)
            logger.info(f"Блок {idx}: ошибка загрузки, отправлено уведомление")

async def main():
    await dp.start_polling(bot, on_startup=on_startup, on_shutdown=on_shutdown)

if __name__ == "__main__":
    asyncio.run(main())