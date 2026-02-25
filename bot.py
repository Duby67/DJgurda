import logging
import html
import signal
import asyncio

from datetime import datetime
from typing import List, Tuple


from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes


from base_handler import BaseHandler

from TikTok import TikTokHandler
from YandexMusic import YandexMusicHandler
from YouTubeShorts import YouTubeShortsHandler
from InstagramReels import InstagramReelsHandler


from processing import split_into_blocks, get_user_link

from tokens import ADMIN_ID, BOT_TOKEN
from logger import setup_logging


setup_logging()
logger = logging.getLogger(__name__)

# Регистрируем все обработчики
handlers: List[BaseHandler] = [
    TikTokHandler(),
    YandexMusicHandler(),
    YouTubeShortsHandler(),
    InstagramReelsHandler(),
]

async def shutdown(app: Application, sig: signal.Signals):
    """Действия перед остановкой бота."""
    logger.info(f"Получен сигнал {sig.name}, завершение работы...")
    try:
        await app.bot.send_message(chat_id=ADMIN_ID, text="⚠️ Бот выключается...")
    except Exception as e:
        logger.error(f"Не удалось отправить уведомление о выключении: {e}")
    # Останавливаем приложение
    await app.stop()
    await app.shutdown()

async def post_init(app: Application):
    """Действия после инициализации бота."""
    # Сохраняем время запуска в bot_data
    app.bot_data['start_time'] = datetime.now()
    try:
        await app.bot.send_message(chat_id=ADMIN_ID, text="✅ Бот успешно запущен и готов к работе!")
        logger.info("Уведомление о запуске отправлено администратору")
    except Exception as e:
        logger.error(f"Не удалось отправить уведомление о запуске: {e}")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Чики-Брики! Отправь ссылку и я все сделаю красиво.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    sources = [handler.source_name for handler in handlers]
    # Форматируем список источников
    sources_text = "\n".join(f"• {source}" for source in sources)
    help_text = (
        "Кидай ссылку и я дам тебе сочный контент\n"
        "Я хаваю:\n"
        f"{sources_text}"
    )
    await update.message.reply_text(help_text)
    
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет время последнего запуска бота."""
    start_time = context.application.bot_data.get('start_time')
    if start_time:
        await update.message.reply_text(
            f"🕒 Бот запущен с: {start_time.strftime('%Y-%m-%d %H:%M:%S')}"
        )
    else:
        await update.message.reply_text("Время запуска неизвестно.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text
    blocks = split_into_blocks(text, handlers)
    if not blocks:
        return

    user_link = get_user_link(update.effective_user)
    chat = update.effective_chat

    # Удаляем исходное сообщение
    try:
        await update.message.delete()
        logger.info("Исходное сообщение удалено")
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение: {e}")

    # Обрабатываем каждый блок отдельно
    for idx, (url, user_context, handler) in enumerate(blocks, start=1):
        # Загружаем контент
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
                    with open(file_info['file_path'], 'rb') as video_file:
                        if file_info.get('thumbnail_path') and file_info['thumbnail_path'].exists():
                            with open(file_info['thumbnail_path'], 'rb') as thumb_file:
                                await chat.send_video(
                                    video=video_file,
                                    caption=caption,
                                    parse_mode=ParseMode.HTML,
                                    thumbnail=thumb_file,
                                    supports_streaming=True
                                )
                        else:
                            await chat.send_video(
                                video=video_file,
                                caption=caption,
                                parse_mode=ParseMode.HTML,
                                supports_streaming=True
                            )
                elif file_info['type'] == 'audio':
                    with open(file_info['file_path'], 'rb') as audio_file:
                        if file_info.get('thumbnail_path') and file_info['thumbnail_path'].exists():
                            with open(file_info['thumbnail_path'], 'rb') as thumb_file:
                                await chat.send_audio(
                                    audio=audio_file,
                                    title=file_info['title'],
                                    performer=file_info['performer'],
                                    thumbnail=thumb_file,
                                    caption=caption,
                                    parse_mode=ParseMode.HTML
                                )
                        else:
                            await chat.send_audio(
                                audio=audio_file,
                                title=file_info['title'],
                                performer=file_info['performer'],
                                caption=caption,
                                parse_mode=ParseMode.HTML
                            )
                elif file_info['type'] == 'photo':
                    with open(file_info['file_path'], 'rb') as photo_file:
                        await chat.send_photo(
                            photo=photo_file,
                            caption=caption,
                            parse_mode=ParseMode.HTML
                        )
                        
                logger.info(f"Блок {idx} успешно отправлен")
            except Exception as e:
                logger.exception(f"Ошибка при отправке контента для {url}")
                # Если ошибка при отправке, шлём текст с ошибкой
                error_text = (f"❌ Не удалось отправить контент.\n\n"
                              f"{user_context}\n\n"
                              f"От ↣ {user_link}\n"
                              f"<a href='{url}'>{handler.source_name}</a>")
                await chat.send_message(text=error_text, parse_mode=ParseMode.HTML)
            finally:
                # Удаляем временные файлы
                handler.cleanup(file_info)
        else:
            # Ошибка загрузки контента
            error_text = (f"❌ Не удалось загрузить контент.\n\n"
                          f"{user_context}\n\n"
                          f"От ↣ {user_link}\n"
                          f"<a href='{url}'>{handler.source_name}</a>")
            await chat.send_message(text=error_text, parse_mode=ParseMode.HTML)
            logger.info(f"Блок {idx}: ошибка загрузки, отправлено уведомление")

def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status_command))
    
    # Обрабатываем все текстовые сообщения, кроме команд
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Бот успешно запущен и готов к работе!")
    app.run_polling(drop_pending_updates=True)
    
    # Регистрация обработчиков сигналов для graceful shutdown
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig, lambda s=sig: asyncio.create_task(shutdown(app, s))
        )

if __name__ == "__main__":
    main()