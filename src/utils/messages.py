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
TITLE_ELIGIBLE_TYPES = frozenset({"video", "photo", "media_group", "shorts", "reels", "stories"})


class SourceHandler(Protocol):
    """Протокол для объектов-обработчиков, используемых при форматировании сообщений."""

    source_name: str


def _remove_hashtags(text: str) -> str:
    """
    Удаляет хэштеги из текста и нормализует пробелы.
    
    Аргументы:
        text: Исходный текст с хэштегами
        
    Возвращает:
        Очищенный текст без хэштегов
    """
    cleaned = HASHTAG_PATTERN.sub('', text)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def _build_safe_title(file_info: Dict[str, Any], source: str) -> str | None:
    """
    Возвращает безопасный заголовок для подписи.

    Для всех источников гарантирует fallback, если после очистки хэштегов
    заголовок пустой или исходный title отсутствует/некорректный.
    """
    fallback_title = f"Контент из {source}" if source else "Контент"

    raw_title = file_info.get('title')
    if not isinstance(raw_title, str):
        return fallback_title

    clean_title = _remove_hashtags(raw_title)
    if clean_title:
        return clean_title

    return fallback_title

def build_caption(
    user_context: str,
    file_info: Dict[str, Any],
    user_link: str,
    url: str,
    handler: SourceHandler
) -> str:
    """
    Строит подпись для медиа-контента.
    
    Аргументы:
        user_context: Контекст сообщения пользователя
        file_info: Информация о файле от обработчика
        user_link: HTML-ссылка на пользователя
        url: Исходный URL
        handler: Обработчик контента
        
    Возвращает:
        HTML-подпись с ограничением длины
    """
    source = handler.source_name
    lines = []
    
    # Добавляем контекст пользователя (если есть)
    if user_context:
        safe_context = html.escape(user_context)
        lines.append(safe_context)
        
    # Для медиа-контента добавляем информацию о названии и авторе.
    if file_info['type'] in TITLE_ELIGIBLE_TYPES:
        safe_title_value = _build_safe_title(file_info, source)
        if safe_title_value:
            lines.append("")  # Пустая строка для разделения
            safe_title = html.escape(safe_title_value)
            uploader = str(file_info.get('uploader') or "").strip()
            if uploader:
                safe_uploader = html.escape(uploader)
                lines.append(f"{EMOJI_VIDEO} {safe_title} — {safe_uploader}")
            else:
                lines.append(f"{EMOJI_VIDEO} {safe_title}")
        
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
    
    Аргументы:
        error_message: Текст ошибки
        url: Проблемный URL
        handler: Обработчик контента
        
    Возвращает:
        HTML-сообщение об ошибке
    """
    source = handler.source_name
    safe_url = html.escape(url, quote=True)
    error_text = (
        f"{EMOJI_ERROR} {error_message}.\n"
        f"{emoji(source)} <a href='{safe_url}'>{source}</a>"
    )
    return error_text
