"""Exercise routing and outgoing messages without contacting Telegram."""

import asyncio
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from unittest.mock import AsyncMock, call

import pytest
from aiogram import Bot
from aiogram.types import Chat, Message, MessageEntity, Update, User

from djgurda import caption, chat
from djgurda.bot import create_dispatcher
from djgurda.chat import HELP
from djgurda.media import Media, MediaError
from djgurda.sources import classify
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
    for match in re.finditer(r"\S+\.\S+/\S*", text):
        entities.append(MessageEntity(type="url", offset=match.start(), length=len(match[0])))
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


def run_script(bot_request: AsyncMock, work_dir: Path, script: list[tuple[int, str]]) -> None:
    async def deliver() -> None:
        async with Bot(token="123456789:offline-test-token") as bot:
            bot.session.make_request = bot_request  # type: ignore[method-assign]
            storage = Storage(work_dir / "db.sqlite3")
            dispatcher = create_dispatcher([100], storage, work_dir)
            for update_id, item in enumerate(script, 1):
                if item == RESTART:
                    storage.close()
                    storage = Storage(work_dir / "db.sqlite3")
                    dispatcher = create_dispatcher([100], storage, work_dir)
                    continue
                chat_id, text = item
                await dispatcher.feed_update(bot, message(update_id, chat_id, text))
            storage.close()

    asyncio.run(deliver())


def sent(request: AsyncMock) -> list[tuple[int, str]]:
    methods = [c.args[1] for c in request.await_args_list]
    return [
        (m.chat_id, getattr(m, "text", None) or getattr(m, "caption", None) or type(m).__name__)
        for m in methods
    ]


def test_chat_lifecycle(tmp_path: Path) -> None:
    request = AsyncMock(return_value=True)
    link = "смотри vm.tiktok.com/abcd"
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

    run_script(request, tmp_path, script)

    status = "Бот {} в этом чате\nВерсия: " + version("djgurda")
    assert sent(request) == [
        (42, "Бот активен в этом чате"),
        (-7, status.format("приостановлен")),
        (-7, HELP),
        (42, status.format("активен")),
        (42, "TikTok: обработка ещё не реализована"),
        (42, "Бот приостановлен в этом чате"),
        (42, status.format("приостановлен")),
        (42, "Бот активен в этом чате"),
        (42, status.format("активен")),
        (-7, status.format("приостановлен")),
    ]


def test_media_delivery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def download(url: str, target: Path) -> Media:
        assert target.parent == tmp_path
        if "fail" in url:
            raise MediaError("не удалось скачать")
        path = target / "video.mp4"
        path.write_bytes(b"video")
        return Media(path, "Title <1>", "Channel", duration=1, width=2, height=3)

    monkeypatch.setattr(chat, "download", download)
    request = AsyncMock(return_value=True)
    author = '<a href="tg://user?id=42">{}</a>'
    source = '<a href="https://youtu.be/ok">YouTube</a>'
    script = [
        (42, "/start"),
        (-7, "/start"),
        (42, "/saymyname  Ivan228 "),
        (42, "как  смешно youtu.be/ok\n\nда"),  # Delivered, so the original is deleted.
        (-7, "youtu.be/ok"),  # The nickname belongs to chat 42 only.
        (42, "youtu.be/ok youtu.be/fail youtube.com/playlist?list=1"),  # Original stays.
        (42, "статья " * 200 + "youtu.be/ok"),  # Too long for a caption: left untouched.
    ]
    run_script(request, tmp_path, script)

    assert sent(request) == [
        (42, "Бот активен в этом чате"),
        (-7, "Бот активен в этом чате"),
        (42, "Имя в этом чате: Ivan228"),
        (
            42,
            f"Title &lt;1&gt; — Channel\n\nкак смешно\nда\n\n{author.format('Ivan228')}\n{source}",
        ),
        (42, "DeleteMessage"),
        (-7, f"Title &lt;1&gt; — Channel\n\n{author.format('Test')}\n{source}"),
        (-7, "DeleteMessage"),
        (42, f"Title &lt;1&gt; — Channel\n\n{author.format('Ivan228')}\n{source}"),
        (42, "YouTube/video: не удалось скачать"),
        (42, "YouTube/playlist: обработка ещё не реализована"),
    ]
    assert not list(tmp_path.glob("download-*"))


def test_caption_fits_telegram_limit() -> None:
    author = caption.Author("Ivan", None)
    text = "т" * 1000
    assert caption.fits(text, author, "YouTube")
    assert not caption.fits(text + "т" * 20, author, "YouTube")
    built = caption.build("Очень длинное название 🎬" * 20, text, author, "YouTube", "https://x")
    visible = built.replace('<a href="https://x">', "").replace("</a>", "")
    assert caption.length(visible) == caption.CAPTION_LIMIT
    assert visible.startswith("Очень") and "…\n\n" in visible


@pytest.mark.parametrize(
    ("url", "label", "downloadable"),
    [
        ("https://www.youtube.com/watch?v=x&list=y", "YouTube/video", True),
        ("youtu.be/x", "YouTube/video", True),
        ("https://m.youtube.com/shorts/x", "YouTube/shorts", True),
        ("https://youtube.com/playlist?list=y", "YouTube/playlist", False),
        ("https://www.youtube.com/@name", "YouTube/channel", False),
        ("https://www.youtube.com/", "YouTube", False),
        ("vm.tiktok.com/abc", "TikTok", False),
        ("HTTPS://M.VK.COM/wall-1_2", "VK", False),
        ("https://notyoutube.com/watch?v=x", None, False),
        ("https://example.com/?u=youtube.com", None, False),
    ],
)
def test_classify(url: str, label: str | None, downloadable: bool) -> None:
    link = classify(url)
    assert (link and link.label) == label
    assert bool(link and link.downloadable) == downloadable


def test_startup_and_shutdown_notify_only_admins(storage: Storage, tmp_path: Path) -> None:
    bot = AsyncMock()
    dispatcher = create_dispatcher([100, 200, 100], storage, tmp_path)
    asyncio.run(dispatcher.emit_startup(bot=bot))
    asyncio.run(dispatcher.emit_shutdown(bot=bot))
    assert bot.send_message.await_args_list == [
        call(chat_id=admin_id, text=f"Бот {event}\nВерсия: {version('djgurda')}")
        for event in ("запущен", "выключен")
        for admin_id in (100, 200)
    ]


def test_startup_notification_failure_is_not_ignored(storage: Storage, tmp_path: Path) -> None:
    bot = AsyncMock()
    bot.send_message.side_effect = RuntimeError("Notification failed")
    with pytest.raises(RuntimeError, match="Notification failed"):
        asyncio.run(create_dispatcher([100], storage, tmp_path).emit_startup(bot=bot))
