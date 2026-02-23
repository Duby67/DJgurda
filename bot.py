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
    extract_urls as youtube_extract,
    parse_urls_with_context as parse_urls
)
from tokens import ADMIN_ID
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

    # Получаем сообщение пользователя и паттерн ссылок
    text = update.message.text
    url_pairs = parse_urls(text)
    if not url_pairs:
        return 
    
    user_link = get_user_link(update.effective_user)
    chat = update.effective_chat
    
    
    successful = []
    errors = []

    for idx, (url, user_text) in enumerate(url_pairs, start=1):
        video_info = await download_video(url)
        if not video_info:
            errors.append(f"❌ Видео {idx}: не удалось загрузить")
            continue

        try:
            # Формируем подпись
            safe_title = html.escape(video_info['title'])
            safe_user_text = html.escape(user_text) if user_text else None

            caption_lines = [f"🎬 {safe_title}"]
            if safe_user_text:
                caption_lines.append(safe_user_text)
            caption_lines.append("")
            caption_lines.append(f"От ↣ {user_link}")
            caption_lines.append(f"<a href='{url}'>Смотреть в YouTube Shorts</a>")
            caption = "\n".join(caption_lines)

            # Отправка видео
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
            successful.append(idx)
        except Exception as e:
            logger.exception(f"Ошибка при отправке {url}")
            errors.append(f"❌ Видео {idx}: внутренняя ошибка")
        finally:
            # Очистка временных файлов
            if video_info.get('file_path'):
                remove_video_file(video_info['file_path'])
            if video_info.get('thumbnail_path'):
                remove_thumbnail_file(video_info['thumbnail_path'])

    # Удаляем исходное сообщение, если хоть одно видео отправилось
    if successful:
        try:
            await update.message.delete()
        except Exception as e:
            logger.warning(f"Не удалось удалить сообщение: {e}")

    # Сообщаем об ошибках, если они были
    if errors:
        error_text = "\n".join(errors)
        if successful:
            await chat.send_message(f"⚠️ При загрузке произошли ошибки:\n{error_text}")
        else:
            await update.message.reply_text(f"❌ Не удалось загрузить ни одного видео.\n{error_text}")


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

async def send_startup_notification(app: Application):
    """Отправляет уведомление администратору о запуске бота."""
    try:
        await app.bot.send_message(
            chat_id=ADMIN_ID,
            text="✅ Бот успешно запущен и готов к работе!"
        )
        logger.info("Уведомление о запуске отправлено администратору")
    except Exception as e:
        logger.error(f"Не удалось отправить уведомление о запуске: {e}")                

def main():
    """Запуск бота."""
    try:
        # Создаём приложение с post_init
        app = (
            Application.builder()
            .token(BOT_TOKEN)
            .post_init(send_startup_notification)
            .build()
        )

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