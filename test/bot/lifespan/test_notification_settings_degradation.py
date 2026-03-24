"""Tests for startup/shutdown notification degradation handling."""

from __future__ import annotations

import asyncio
import importlib
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

# test/bot/lifespan/test_notification_settings_degradation.py -> project root это parents[3]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Минимальные env для загрузки src.config.
os.environ.setdefault("BOT_DB_PATH", str(PROJECT_ROOT / "src" / "data" / "db" / "bot.db"))
os.environ.setdefault("BOT_VERSION", "local-test")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("BOT_TOKEN", "local-test-token")
os.environ.setdefault("YANDEX_MUSIC_TOKEN", "local-test-token")

startup_module = importlib.import_module("src.bot.lifespan.startup")
shutdown_module = importlib.import_module("src.bot.lifespan.shutdown")


class FakeBot:
    """Минимальный fake bot для проверки send_message."""

    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> None:
        self.messages.append((chat_id, text))


def test_startup_still_notifies_admin_when_notification_settings_unavailable(monkeypatch: Any) -> None:
    """Startup should continue with admin notification even if chat list read fails."""

    bot = FakeBot()

    async def noop_async(*_args: Any, **_kwargs: Any) -> None:
        return None

    async def fake_get_chats() -> list[int]:
        raise startup_module.SettingsReadError("database unavailable", column="notifications_enabled")

    monkeypatch.setattr(startup_module, "cleanup_expired_temp_files", lambda *_args: None)
    monkeypatch.setattr(startup_module, "ensure_runtime_storage", lambda *_args: None)
    monkeypatch.setattr(startup_module, "init_db", noop_async)
    monkeypatch.setattr(startup_module, "get_active_handler_names", lambda: ["YouTube"])
    monkeypatch.setattr(startup_module, "get_chats_with_notifications_enabled", fake_get_chats)

    asyncio.run(startup_module.on_startup(bot))

    assert bot.messages == [
        (
            startup_module.ADMIN_ID,
            f"{startup_module.EMOJI_SUCCESS} Бот успешно запущен и готов к работе!",
        )
    ]
    assert bot.start_time is not None


def test_shutdown_still_notifies_admin_when_notification_settings_unavailable(monkeypatch: Any) -> None:
    """Shutdown should continue with admin notification even if chat list read fails."""

    bot = FakeBot()
    dispatcher = SimpleNamespace()

    async def noop_async(*_args: Any, **_kwargs: Any) -> None:
        return None

    async def fake_get_chats() -> list[int]:
        raise shutdown_module.SettingsReadError("database unavailable", column="notifications_enabled")

    monkeypatch.setattr(shutdown_module, "cleanup_all_temp_files", lambda: None)
    monkeypatch.setattr(shutdown_module, "close_db", noop_async)
    monkeypatch.setattr(shutdown_module, "get_chats_with_notifications_enabled", fake_get_chats)

    asyncio.run(shutdown_module.on_shutdown(bot, dispatcher))

    assert bot.messages == [
        (shutdown_module.ADMIN_ID, f"{shutdown_module.EMOJI_WARNING} Бот выключается...")
    ]
