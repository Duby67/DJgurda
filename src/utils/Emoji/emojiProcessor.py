"""
Процессор для работы с эмодзи.

Генерирует HTML-разметку для кастомных Telegram-эмодзи с резервным вариантом на стандартные.
"""

import logging
from typing import Dict, Any
from .emojiData import EMOJI_DATA, DEFAULT_KEY

logger = logging.getLogger(__name__)

def _make_emoji_dict(emoji_list: list) -> Dict[str, Dict[str, Any]]:
    """
    Создает словарь эмодзи из списка данных.
    
    Аргументы:
        emoji_list: Список кортежей с данными эмодзи
        
    Возвращает:
        Словарь вида {ключ: {"emoji": "символ", "custom_id": id}}
    """
    result = {}
    for item in emoji_list:
        if len(item) == 3:
            key, emoji_char, custom_id = item
        else:
            key, emoji_char = item
            custom_id = None
        result[key] = {"emoji": emoji_char, "custom_id": custom_id}
    return result

# Глобальный словарь эмодзи
SOURCE_EMOJI = _make_emoji_dict(EMOJI_DATA)

def _get_emoji_data(key: str) -> Dict[str, Any]:
    """
    Получает данные эмодзи по ключу.
    
    Аргументы:
        key: Ключ эмодзи
        
    Возвращает:
        Словарь с данными эмодзи или данные по умолчанию
    """
    return SOURCE_EMOJI.get(key, SOURCE_EMOJI[DEFAULT_KEY])

def emoji(key: str) -> str:
    """
    Генерирует HTML-разметку для эмодзи.
    
    Использует кастомный Telegram Emoji ID если доступен, иначе стандартный символ.
    
    Аргументы:
        key: Ключ эмодзи из базы данных
        
    Возвращает:
        HTML-строка с разметкой эмодзи или обычный эмодзи-символ
    """
    data = _get_emoji_data(key)
    fallback = data["emoji"]
    custom_id = data.get("custom_id")
    
    if custom_id:
        # Генерируем разметку для кастомного эмодзи
        return f'<tg-emoji emoji-id="{custom_id}">{fallback}</tg-emoji>'
    else:
        # Логируем использование резервного варианта
        logger.debug(f"Для ключа '{key}' используется стандартный эмодзи: {fallback}")
        return fallback
