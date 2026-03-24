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


class SessionContext:
    """Минимальный async-session context для settings tests."""

    def __init__(self, session: Any) -> None:
        self.session = session

    async def __aenter__(self) -> Any:
        return self.session

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False


class BeginContext:
    """Контекст для session.begin()."""

    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False


class CountingSettingsSession:
    """Фейковая session с подсчетом чтений BotSettings."""

    def __init__(self) -> None:
        self.get_calls: list[int] = []
        self.settings_by_chat: dict[int, Any] = {}

    async def get(self, _model: Any, chat_id: int) -> Any:
        self.get_calls.append(chat_id)
        return self.settings_by_chat.get(chat_id)

    def begin(self) -> BeginContext:
        return BeginContext()

    def add(self, settings: Any) -> None:
        self.settings_by_chat[settings.chat_id] = settings


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


def test_settings_cache_scope_reuses_single_db_read_for_multiple_getters(monkeypatch: Any) -> None:
    """Scoped cache должен схлопывать несколько getter-ов в один DB read."""

    session = CountingSettingsSession()
    session.settings_by_chat[123] = SimpleNamespace(
        chat_id=123,
        bot_enabled=True,
        errors_enabled=False,
        notifications_enabled=True,
    )
    monkeypatch.setattr(bot_settings_module, "AsyncSessionLocal", lambda: SessionContext(session))

    async def scenario() -> None:
        async with bot_settings_module.settings_cache_scope():
            assert await bot_settings_module.get_bot_enabled(123) is True
            assert await bot_settings_module.get_errors_enabled(123) is False
            assert await bot_settings_module.get_notifications_enabled(123) is True

    asyncio.run(scenario())

    assert session.get_calls == [123]


def test_bot_enabled_middleware_shares_settings_cache_with_handler(monkeypatch: Any) -> None:
    """Middleware scope должен переиспользоваться внутри downstream handler flow."""

    session = CountingSettingsSession()
    session.settings_by_chat[123] = SimpleNamespace(
        chat_id=123,
        bot_enabled=True,
        errors_enabled=True,
        notifications_enabled=False,
    )
    monkeypatch.setattr(bot_settings_module, "AsyncSessionLocal", lambda: SessionContext(session))
    monkeypatch.setattr(bot_enabled_middleware_module, "get_bot_enabled", bot_settings_module.get_bot_enabled)

    async def handler(_event: Any, _data: dict[str, Any]) -> tuple[bool, bool]:
        return (
            await bot_settings_module.get_errors_enabled(123),
            await bot_settings_module.get_notifications_enabled(123),
        )

    result = asyncio.run(
        bot_enabled_middleware_module.BotEnabledMiddleware()(handler, FakeMessage(), {})
    )

    assert result == (True, False)
    assert session.get_calls == [123]


def test_set_setting_updates_cached_snapshot_inside_scope(monkeypatch: Any) -> None:
    """Write-path должен обновлять scoped cache, а не оставлять stale read."""

    session = CountingSettingsSession()
    session.settings_by_chat[123] = SimpleNamespace(
        chat_id=123,
        bot_enabled=True,
        errors_enabled=False,
        notifications_enabled=False,
    )
    monkeypatch.setattr(bot_settings_module, "AsyncSessionLocal", lambda: SessionContext(session))

    async def scenario() -> None:
        async with bot_settings_module.settings_cache_scope():
            assert await bot_settings_module.get_errors_enabled(123) is False
            await bot_settings_module.set_errors_enabled(123, True)
            assert await bot_settings_module.get_errors_enabled(123) is True

    asyncio.run(scenario())

    assert session.get_calls == [123, 123]
