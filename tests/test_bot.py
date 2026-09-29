"""Exercise routing and outgoing messages without contacting Telegram."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from aiogram.methods import SendMessage
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
            await create_dispatcher().feed_update(bot, update)

    asyncio.run(deliver())

    if text == "/start":
        request.assert_awaited_once()
        method = request.await_args.args[1]
        assert isinstance(method, SendMessage)
        assert method.chat_id == 42
        assert method.text == "Hello world"
    else:
        request.assert_not_awaited()
