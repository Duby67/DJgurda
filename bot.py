import logging
import html
from typing import List, Tuple


from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes


from base_handler import BaseHandler
from YandexMusic import YandexMusicHandler
from YouTubeShorts import YouTubeShortsHandler


from processing import split_into_blocks, get_user_link


from tokens import ADMIN_ID, BOT_TOKEN
from logger import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

# Регистрируем все обработчики (должны быть экземплярами BaseHandler)
handlers: List[BaseHandler] = [
    YouTubeShortsHandler(),
    YandexMusicHandler(),
]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Чики-Брики! Отправь ссылку и я все сделаю красиво.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text
    blocks = split_into_blocks(text, handlers)
    if not blocks:
        return  # нет ссылок

    user_link = get_user_link(update.effective_user)
    chat = update.effective_chat

    successful = []
    errors = []

    for idx, (url, user_context, handler) in enumerate(blocks, start=1):
        # Загружаем контент
        file_info = await handler.process(url, user_context)
        if not file_info:
            errors.append(f"❌ Блок {idx}: не удалось загрузить ({url})")
            continue

        try:
            # Формируем подпись
            caption_lines = []
            if user_context:
                safe_context = html.escape(user_context)
                caption_lines.append(safe_context)

            if file_info['type'] == 'video':
                safe_title = html.escape(file_info['title'])
                safe_uploader = html.escape(file_info['uploader'])
                caption_lines.append(f"🎬 {safe_title} — {safe_uploader}")
            elif file_info['type'] == 'audio':
                safe_title = html.escape(file_info['title'])
                safe_artist = html.escape(file_info['performer'])
                caption_lines.append(f"🎵 {safe_title} — {safe_artist}")

            caption_lines.append("")
            caption_lines.append(f"От ↣ {user_link}")
            caption_lines.append(f"<a href='{url}'>Оригинал</a>")
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
            successful.append(idx)
        except Exception as e:
            logger.exception(f"Ошибка при отправке контента для {url}")
            errors.append(f"❌ Блок {idx}: ошибка отправки")
        finally:
            # Удаляем временные файлы
            handler.cleanup(file_info)

    # Удаляем исходное сообщение, если хоть один блок обработан успешно
    if successful:
        try:
            await update.message.delete()
        except Exception as e:
            logger.warning(f"Не удалось удалить сообщение: {e}")

    # Отправляем отчёт об ошибках
    if errors:
        error_text = "\n".join(errors)
        if successful:
            await chat.send_message(f"⚠️ При загрузке произошли ошибки:\n{error_text}")
        else:
            await update.message.reply_text(f"❌ Не удалось загрузить ни одного элемента.\n{error_text}")

async def send_startup_notification(app: Application):
    """Уведомление администратору о запуске."""
    try:
        await app.bot.send_message(chat_id=ADMIN_ID, text="✅ Бот успешно запущен и готов к работе!")
        logger.info("Уведомление о запуске отправлено администратору")
    except Exception as e:
        logger.error(f"Не удалось отправить уведомление о запуске: {e}")

def main():
    app = Application.builder().token(BOT_TOKEN).post_init(send_startup_notification).build()
    app.add_handler(CommandHandler("start", start))
    # Обрабатываем все текстовые сообщения, кроме команд
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Бот успешно запущен и готов к работе!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()