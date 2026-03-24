"""Tests for safe toggle behavior when settings reads are degraded."""

from __future__ import annotations

import asyncio
import importlib
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

# test/bot/commands/test_toggle_settings_degradation.py -> project root это parents[3]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Минимальные env для загрузки src.config.
os.environ.setdefault("BOT_DB_PATH", str(PROJECT_ROOT / "src" / "data" / "db" / "bot.db"))
os.environ.setdefault("BOT_VERSION", "local-test")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("BOT_TOKEN", "local-test-token")
os.environ.setdefault("YANDEX_MUSIC_TOKEN", "local-test-token")


class FakeMessage:
    """Минимальная модель Message для toggle-команд."""

    def __init__(self) -> None:
        self.chat = SimpleNamespace(id=321)
        self.from_user = SimpleNamespace(id=654)
        self.replies: list[str] = []

    async def reply(self, text: str) -> None:
        self.replies.append(text)


@pytest.mark.parametrize(
    "module_path,command_name,getter_name,setter_name,error_snippet",
    [
        (
            "src.bot.commands.toggle_bot",
            "cmd_toggle_bot",
            "get_bot_enabled",
            "set_bot_enabled",
            "Не удалось прочитать текущее состояние бота",
        ),
        (
            "src.bot.commands.toggle_errors",
            "cmd_toggle_errors",
            "get_errors_enabled",
            "set_errors_enabled",
            "Не удалось прочитать текущее состояние ошибок",
        ),
        (
            "src.bot.commands.toggle_notifications",
            "cmd_toggle_notifications",
            "get_notifications_enabled",
            "set_notifications_enabled",
            "Не удалось прочитать текущее состояние уведомлений",
        ),
    ],
)
def test_toggle_commands_abort_when_settings_cannot_be_read(
    module_path: str,
    command_name: str,
    getter_name: str,
    setter_name: str,
    error_snippet: str,
    monkeypatch: Any,
) -> None:
    """Toggle-команды не должны инвертировать неизвестное состояние."""

    module = importlib.import_module(module_path)
    called = False

    async def fake_getter(_chat_id: int) -> bool:
        raise module.SettingsReadError("database unavailable", chat_id=321, column=getter_name)

    async def fake_setter(_chat_id: int, _new_state: bool) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(module, getter_name, fake_getter)
    monkeypatch.setattr(module, setter_name, fake_setter)

    message = FakeMessage()
    asyncio.run(getattr(module, command_name)(message))

    assert called is False
    assert len(message.replies) == 1
    assert error_snippet in message.replies[0]
