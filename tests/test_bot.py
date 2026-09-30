"""Exercise routing and outgoing messages without contacting Telegram."""

import asyncio
from datetime import datetime, timezone
from importlib.metadata import version
from unittest.mock import AsyncMock, call

import pytest
from aiogram import Bot
from aiogram.types import Chat, Message, MessageEntity, Update, User

from djgurda.bot import create_dispatcher


@pytest.mark.parametrize("text", ["/start", "ordinary text"])
def test_message_routing(text: str, monkeypatch: pytest.MonkeyPatch) -> None:
    request = AsyncMock(return_value=True)

    async def deliver() -> None:
        async with Bot(token="123456789:offline-test-token") as bot:
            monkeypatch.setattr(bot.session, "make_request", request)
            update = Update(
                update_id=1,
                message=Message(
                    message_id=1,
                    date=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    chat=Chat(id=42, type="private"),
                    from_user=User(id=42, is_bot=False, first_name="Test"),
                    text=text,
                    entities=[MessageEntity(type="bot_command", offset=0, length=6)]
                    if text == "/start" else [],
                ),
            )
            await create_dispatcher([100]).feed_update(bot, update)

    asyncio.run(deliver())

    request.assert_not_awaited()


def test_startup_notifies_only_admins() -> None:
    bot = AsyncMock()
    dispatcher = create_dispatcher([100, 200, 100])
    asyncio.run(dispatcher.emit_startup(bot=bot))
    assert bot.send_message.await_args_list == [
        call(chat_id=admin_id, text=f"Бот запущен\nВерсия: {version('djgurda')}")
        for admin_id in (100, 200)
    ]


def test_startup_notification_failure_is_not_ignored() -> None:
    bot = AsyncMock()
    bot.send_message.side_effect = RuntimeError("Notification failed")
    with pytest.raises(RuntimeError, match="Notification failed"):
        asyncio.run(create_dispatcher([100]).emit_startup(bot=bot))
