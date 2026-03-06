"""
Утилиты для форматирования сообщений и подписей.

Содержит функции для создания подписей к медиа и сообщений об ошибках
с учетом ограничений Telegram и безопасной HTML-разметкой.
"""

import re
import html
from typing import Any, Dict, Protocol

from src.config import MAX_CAPTION
from src.utils.Emoji import emoji, EMOJI_ERROR, EMOJI_VIDEO, EMOJI_ARROW

# Паттерн для поиска хэштегов
HASHTAG_PATTERN = re.compile(r'#\w+')


class SourceHandler(Protocol):
    """Protocol for handler objects used in message formatting."""

    source_name: str


def _remove_hashtags(text: str) -> str:
    """
    Удаляет хэштеги из текста и нормализует пробелы.
    
    Args:
        text: Исходный текст с хэштегами
        
    Returns:
        Очищенный текст без хэштегов
    """
    cleaned = HASHTAG_PATTERN.sub('', text)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned

def build_caption(
    user_context: str,
    file_info: Dict[str, Any],
    user_link: str,
    url: str,
    handler: SourceHandler
) -> str:
    """
    Строит подпись для медиа-контента.
    
    Args:
        user_context: Контекст сообщения пользователя
        file_info: Информация о файле от обработчика
        user_link: HTML-ссылка на пользователя
        url: Исходный URL
        handler: Обработчик контента
        
    Returns:
        HTML-подпись с ограничением длины
    """
    source = handler.source_name
    lines = []
    
    # Добавляем контекст пользователя (если есть)
    if user_context:
        safe_context = html.escape(user_context)
        lines.append(safe_context)
        
    # Для видео добавляем информацию о названии и авторах
    if file_info['type'] == 'video':
        lines.append("")  # Пустая строка для разделения
        clean_title = _remove_hashtags(file_info['title'])
        safe_title = html.escape(clean_title)
        safe_uploader = html.escape(file_info['uploader'])
        lines.append(f"{EMOJI_VIDEO} {safe_title} — {safe_uploader}")
        
    # Добавляем информацию об источнике и пользователе
    lines.append("")
    lines.append(f"{EMOJI_ARROW} {user_link}")
    safe_url = html.escape(url, quote=True)
    lines.append(f"{emoji(source)} <a href='{safe_url}'>{source}</a>")
    
    # Собираем подпись
    caption = "\n".join(lines)
    
    # Проверяем длину и обрезаем если нужно
    if len(caption) > MAX_CAPTION:
        caption = caption[:MAX_CAPTION-3] + "..."
    
    return caption

def build_error(
    error_message: str,
    url: str,
    handler: SourceHandler
) -> str:
    """
    Строит сообщение об ошибке.
    
    Args:
        error_message: Текст ошибки
        url: Проблемный URL
        handler: Обработчик контента
        
    Returns:
        HTML-сообщение об ошибке
    """
    source = handler.source_name
    safe_url = html.escape(url, quote=True)
    error_text = (
        f"{EMOJI_ERROR} {error_message}.\n"
        f"{emoji(source)} <a href='{safe_url}'>{source}</a>"
    )
    return error_text
