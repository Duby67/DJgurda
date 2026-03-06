"""
Настройка логирования для бота.

Предоставляет функцию для централизованной настройки логирования
со стандартным форматированием и обработчиками.
"""

import sys
import logging
from typing import Optional

def setup_logging(level: int = logging.INFO, log_file: Optional[str] = None) -> None:
    """
    Настраивает базовое логирование для бота.
    
    Args:
        level: Уровень логирования (по умолчанию INFO)
        log_file: Путь к файлу для записи логов (опционально)
    """
    handlers = [logging.StreamHandler(sys.stdout)]
    
    # Добавляем файловый обработчик если указан
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=level,
        handlers=handlers,
        force=True,
    )
    
    # Устанавливаем уровень для aiohttp и подобных библиотек
    logging.getLogger('aiohttp').setLevel(logging.WARNING)
    logging.getLogger('asyncio').setLevel(logging.WARNING)
