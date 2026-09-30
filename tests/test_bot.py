"""Exercise routing and outgoing messages without contacting Telegram."""

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from unittest.mock import AsyncMock, call

import pytest
from aiogram import Bot
from aiogram.types import Chat, Message, MessageEntity, Update, User

from djgurda.bot import create_dispatcher
from djgurda.chat import HELP
from djgurda.links import classify
from djgurda.storage import Storage

RESTART = (0, "")


@pytest.fixture
def storage(tmp_path: Path) -> Iterator[Storage]:
    storage = Storage(tmp_path / "db.sqlite3")
    yield storage
    storage.close()


def message(update_id: int, chat_id: int, text: str) -> Update:
    entities = []
    if text.startswith("/"):
        entities.append(MessageEntity(type="bot_command", offset=0, length=len(text.split()[0])))
    if "youtu.be" in text:
        entities.append(MessageEntity(type="url", offset=text.index("youtu.be"), length=12))
    return Update(
        update_id=update_id,
        message=Message(
            message_id=update_id,
            date=datetime(2026, 1, 1, tzinfo=UTC),
            chat=Chat(id=chat_id, type="group" if chat_id < 0 else "private"),
            from_user=User(id=42, is_bot=False, first_name="Test"),
            text=text,
            entities=entities,
        ),
    )


def test_chat_lifecycle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    request = AsyncMock(return_value=True)
    link = "смотри youtu.be/abcd"
    script = [
        (42, link),
        (42, "/stop"),  # Paused until /start.
        (42, "/start"),
        (-7, "/status"),  # Another chat stays paused.
        (-7, "/help"),
        (42, "/status"),
        (42, link),
        (42, "/stop"),
        (42, "/status"),
        (42, link),
        (42, "/start"),
        RESTART,  # Chat state survives a restart.
        (42, "/status"),
        (-7, "/status"),
    ]

    async def deliver() -> None:
        async with Bot(token="123456789:offline-test-token") as bot:
            monkeypatch.setattr(bot.session, "make_request", request)
            storage = Storage(tmp_path / "db.sqlite3")
            dispatcher = create_dispatcher([100], storage)
            for update_id, item in enumerate(script, 1):
                if item == RESTART:
                    storage.close()
                    storage = Storage(tmp_path / "db.sqlite3")
                    dispatcher = create_dispatcher([100], storage)
                    continue
                chat_id, text = item
                await dispatcher.feed_update(bot, message(update_id, chat_id, text))
            storage.close()

    asyncio.run(deliver())

    sent = [(c.args[1].chat_id, c.args[1].text) for c in request.await_args_list]
    status = "Бот {} в этом чате\nВерсия: " + version("djgurda")
    assert sent == [
        (42, "Бот активен в этом чате"),
        (-7, status.format("приостановлен")),
        (-7, HELP),
        (42, status.format("активен")),
        (42, "YouTube: обработка ещё не реализована"),
        (42, "Бот приостановлен в этом чате"),
        (42, status.format("приостановлен")),
        (42, "Бот активен в этом чате"),
        (42, status.format("активен")),
        (-7, status.format("приостановлен")),
    ]


@pytest.mark.parametrize(
    ("url", "source"),
    [
        ("https://www.youtube.com/watch?v=x", "YouTube"),
        ("vm.tiktok.com/abc", "TikTok"),
        ("HTTPS://M.VK.COM/wall-1_2", "VK"),
        ("https://music.yandex.ru/album/1", "Yandex Music"),
        ("https://notyoutube.com/watch", None),
        ("https://example.com/?u=youtube.com", None),
    ],
)
def test_classify(url: str, source: str | None) -> None:
    result = classify(url)
    assert (result and result.name) == source


def test_startup_notifies_only_admins(storage: Storage) -> None:
    bot = AsyncMock()
    dispatcher = create_dispatcher([100, 200, 100], storage)
    asyncio.run(dispatcher.emit_startup(bot=bot))
    assert bot.send_message.await_args_list == [
        call(chat_id=admin_id, text=f"Бот запущен\nВерсия: {version('djgurda')}")
        for admin_id in (100, 200)
    ]


def test_startup_notification_failure_is_not_ignored(storage: Storage) -> None:
    bot = AsyncMock()
    bot.send_message.side_effect = RuntimeError("Notification failed")
    with pytest.raises(RuntimeError, match="Notification failed"):
        asyncio.run(create_dispatcher([100], storage).emit_startup(bot=bot))
