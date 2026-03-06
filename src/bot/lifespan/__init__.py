"""
Модуль жизненного цикла бота.

Содержит обработчики запуска и остановки бота.
"""

from .startup import on_startup
from .shutdown import on_shutdown

__all__ = ["on_startup", "on_shutdown"]