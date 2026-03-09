"""Адаптеры совместимости для handler-результатов."""

from .legacy_file_info import LegacyFileInfoAdapter, adapt_handler_output

__all__ = ["LegacyFileInfoAdapter", "adapt_handler_output"]
