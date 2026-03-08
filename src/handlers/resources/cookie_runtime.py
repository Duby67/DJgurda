"""
Совместимый re-export runtime-helper для cookies.

Основная реализация перенесена в `src.utils.cookies`.
"""

from src.utils.cookies import prepare_cookiefile_for_ytdlp

__all__ = ["prepare_cookiefile_for_ytdlp"]
