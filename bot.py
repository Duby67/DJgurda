import logging
import html

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from YandexMusic import (
    get_music_file, 
    remove_music_file, 
    get_url_pattern, 
    extract_url, 
    remove_cover_file
)

from YouTubeShorts import (
    download_video,
    remove_video_file,
    remove_thumbnail_file,
    get_url_pattern as youtube_pattern,
    extract_url as youtube_extract,
)

from tokens import BOT_TOKEN
from logger import setup_logging

# Настраиваем логирование
setup_logging()
logger = logging.getLogger(__name__)


def get_user_link(user) -> str:
    """Возвращает строку с именем и ссылкой на профиль пользователя."""
    name = user.full_name
    if user.username:
        return f'<a href="https://t.me/{user.username}">{name}</a>'
    return name


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start."""
    await update.message.reply_text("Чики-Брики! Отправь ссылку и я все сделаю красиво.")


async def handle_youtube_shorts_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text
    url = youtube_extract(text)
    if not url:
        return

    # Удаляем исходное сообщение с ссылкой
    try:
        await update.message.delete()
        logger.info("Исходное сообщение с YouTube Shorts удалено")
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение: {e}")

    # Отправляем статусное сообщение
    chat = update.effective_chat
    status_msg = await chat.send_message("📥 Загружаю видео...")

    video_info = None
    try:
        video_info = await download_video(url)
        if not video_info:
            await status_msg.edit_text("❌ Не удалось загрузить видео. Проверьте ссылку или попробуйте позже.")
            return
        
        # Экранируем название видео
        safe_title = html.escape(video_info['title'])
        
        # Формируем подпись: теперь с названием
        user_link = get_user_link(update.effective_user)
        caption = (f"🎬 {safe_title}\n\n"
                   f"От ↣ {user_link}\n"
                   f"<a href='{url}'>Смотреть в YouTube Shorts</a>")
        
        # Отправляем видео
        with open(video_info['file_path'], 'rb') as video_file:
            if video_info['thumbnail_path'] and video_info['thumbnail_path'].exists():
                with open(video_info['thumbnail_path'], 'rb') as thumb_file:
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

        # Удаляем статусное сообщение
        await status_msg.delete()

    except Exception as e:
        logger.exception("Ошибка при обработке ссылки YouTube Shorts")
        await status_msg.edit_text("❌ Произошла внутренняя ошибка. Попробуйте позже.")
    finally:
        # Очищаем временные файлы
        if video_info:
            if video_info['file_path']:
                remove_video_file(video_info['file_path'])
            if video_info['thumbnail_path']:
                remove_thumbnail_file(video_info['thumbnail_path'])


async def handle_yandex_music_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text
    url = extract_url(text)
    if not url:
        return

    # Пытаемся удалить сообщение с ссылкой
    try:
        await update.message.delete()
        logger.info("Исходное сообщение удалено")
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение: {e}")

    # Отправляем статусное сообщение
    chat = update.effective_chat
    status_msg = await chat.send_message("🎵 Загружаю музыку...")

    file_info = None
    try:
        file_info = await get_music_file(url)
        if not file_info:
            await status_msg.edit_text("❌ Не удалось загрузить трек. Проверьте ссылку или попробуйте позже.")
            return
        
        # Экранируем название и исполнителя
        safe_title = html.escape(file_info['title'])
        safe_artist = html.escape(file_info['artist'])
        
        # Формируем подпись
        user_link = get_user_link(update.effective_user)
        caption = (f"От ↣ {user_link}\n"
                   f"<a href='{url}'>Слушать в Яндекс.Музыка</a>")
        title = file_info['title']
        performer = file_info['artist']
        
        # Отправляем аудио с обложкой
        with open(file_info['file_path'], 'rb') as audio_file:
            # Для thumbnail нужно открыть файл обложки, если он есть
            if file_info['cover_path'] and file_info['cover_path'].exists():
                with open(file_info['cover_path'], 'rb') as thumb_file:
                    await chat.send_audio(
                        audio=audio_file,
                        title=title,
                        performer=performer,
                        thumbnail=thumb_file,
                        caption=caption,
                        parse_mode=ParseMode.HTML
                    )
            else:
                await chat.send_audio(
                    audio=audio_file,
                    title=title,
                    performer=performer,
                    caption=caption,
                    parse_mode=ParseMode.HTML
                )

        # Удаляем статусное сообщение
        await status_msg.delete()

    except Exception as e:
        logger.exception("Ошибка при обработке ссылки")
        await status_msg.edit_text("❌ Произошла внутренняя ошибка. Попробуйте позже.")
    finally:
        # Удаляем временные файлы
        if file_info:
            if file_info['file_path']:
                remove_music_file(file_info['file_path'])
            if file_info['cover_path']:
                remove_cover_file(file_info['cover_path'])
                

def main():
    """Запуск бота."""
    try:
        # Создаём приложение
        app = Application.builder().token(BOT_TOKEN).build()

        # Добавляем обработчики
        app.add_handler(CommandHandler("start", start))
        app.add_handler(MessageHandler(
            filters.TEXT & filters.Regex(get_url_pattern()),
            handle_yandex_music_link
        ))
        app.add_handler(MessageHandler(
            filters.TEXT & filters.Regex(youtube_pattern()),
            handle_youtube_shorts_link
        ))

        logger.info("Бот успешно запущен и готов к работе!")
        
        # Запускаем бота
        app.run_polling(drop_pending_updates=True)
        
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
        raise


if __name__ == "__main__":
    main()