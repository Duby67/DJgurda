"""Readiness covers initialization, failure and process cleanup without Telegram."""

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from aiogram import Dispatcher

from djgurda import __main__ as app
from djgurda.config import Settings


@pytest.mark.parametrize("failure", [None, "identity", "notification", "polling"])
def test_readiness_lifecycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str | None
) -> None:
    marker = tmp_path / "ready"
    marker.touch()  # A restart must discard readiness from the previous process.
    monkeypatch.setattr(app, "READY_FILE", marker)
    bot = AsyncMock()
    bot.__aenter__.return_value = bot
    monkeypatch.setattr(app, "Bot", lambda **kwargs: bot)

    async def identity() -> None:
        assert not marker.exists()
        if failure == "identity":
            raise RuntimeError("identity failed")

    async def notify(**kwargs: Any) -> None:
        assert not marker.exists()
        if failure == "notification":
            raise RuntimeError("notification failed")

    bot.me.side_effect = identity
    bot.send_message.side_effect = notify

    async def polling(dispatcher: Dispatcher, bot: AsyncMock, **kwargs: Any) -> None:
        assert not marker.exists()
        await dispatcher.emit_startup(bot=bot)
        assert marker.exists()
        if failure == "polling":
            raise RuntimeError("polling failed")

    monkeypatch.setattr(Dispatcher, "start_polling", polling)
    settings = Settings(bot_token="123:offline-token", admin_ids=[100], _env_file=None)
    if failure:
        with pytest.raises(RuntimeError, match=failure):
            asyncio.run(app.run(settings))
    else:
        asyncio.run(app.run(settings))
    assert not marker.exists()
    bot.delete_webhook.assert_awaited_once_with(drop_pending_updates=True)
    bot.__aexit__.assert_awaited_once()
