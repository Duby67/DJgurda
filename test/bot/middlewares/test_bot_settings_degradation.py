"""Tests for explicit degradation behavior in bot settings reads."""

from __future__ import annotations

import asyncio
import importlib
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

# test/bot/middlewares/test_bot_settings_degradation.py -> project root это parents[3]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Минимальные env для загрузки src.config.
os.environ.setdefault("BOT_DB_PATH", str(PROJECT_ROOT / "src" / "data" / "db" / "bot.db"))
os.environ.setdefault("BOT_VERSION", "local-test")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("BOT_TOKEN", "local-test-token")
os.environ.setdefault("YANDEX_MUSIC_TOKEN", "local-test-token")
os.environ.setdefault("YOUTUBE_COOKIES_ENABLED", "false")

bot_settings_module = importlib.import_module("src.middlewares.db.processing.bot_settings_processor")
bot_enabled_middleware_module = importlib.import_module("src.middlewares.bot_enabled")


class FailingSessionContext:
    """Контекст, который падает при входе в async session."""

    async def __aenter__(self) -> Any:
        raise RuntimeError("database unavailable")

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False


class FakeMessage:
    """Минимальная модель aiogram Message для теста middleware."""

    def __init__(self, text: str | None = "hello") -> None:
        self.text = text
        self.chat = SimpleNamespace(id=123)
        self.answers: list[str] = []


def test_get_bot_enabled_raises_settings_read_error_on_db_failure(monkeypatch: Any) -> None:
    """DB failures should surface as explicit settings read errors."""

    monkeypatch.setattr(bot_settings_module, "AsyncSessionLocal", lambda: FailingSessionContext())

    with pytest.raises(bot_settings_module.SettingsReadError) as excinfo:
        asyncio.run(bot_settings_module.get_bot_enabled(123))

    assert excinfo.value.chat_id == 123
    assert excinfo.value.column == "bot_enabled"


def test_bot_enabled_middleware_allows_message_when_settings_unavailable(monkeypatch: Any) -> None:
    """Middleware should fail open explicitly when bot settings cannot be read."""

    called = False

    async def handler(event: Any, data: dict[str, Any]) -> str:
        nonlocal called
        called = True
        return "handled"

    async def fake_get_bot_enabled(_chat_id: int) -> bool:
        raise bot_settings_module.SettingsReadError("database unavailable", chat_id=123, column="bot_enabled")

    monkeypatch.setattr(bot_enabled_middleware_module, "get_bot_enabled", fake_get_bot_enabled)

    result = asyncio.run(
        bot_enabled_middleware_module.BotEnabledMiddleware()(handler, FakeMessage(), {})
    )

    assert called is True
    assert result == "handled"
