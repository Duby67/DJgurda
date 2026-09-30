"""Exercise routing and outgoing messages without contacting Telegram."""

import asyncio
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, call

import pytest
from aiogram import Bot
from aiogram.methods import SendChatAction, SendVideo, TelegramMethod
from aiogram.types import Chat, FSInputFile, Message, MessageEntity, PhotoSize, Update, User, Video

from djgurda import caption, chat
from djgurda.bot import create_dispatcher
from djgurda.chat import HELP
from djgurda.media import Info, Media, MediaError
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
        if not isinstance(m, SendChatAction)  # Timing-dependent progress indicator.
    ]


async def telegram(bot: Bot, method: TelegramMethod[Any], timeout: int | None = None) -> Any:
    if isinstance(method, SendVideo):  # The bot caches the returned file_id.
        cover = [PhotoSize(file_id="cover-1", file_unique_id="c", width=4, height=3)]
        video = Video(
            file_id="file-1", file_unique_id="u", width=2, height=3, duration=1, cover=cover
        )
        return Message(
            message_id=99, date=datetime.now(UTC), chat=Chat(id=1, type="private"), video=video
        )
    return True


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
    downloads = []

    def download(url: str, target: Path) -> Media:
        assert target.parent == tmp_path
        downloads.append(url)
        if "fail" in url:
            raise MediaError("не удалось скачать")
        path, cover, thumbnail = target / "video.mp4", target / "cover.jpg", target / "thumb.jpg"
        info = Info("Title <1>", "Channel", duration=1, width=2, height=3)
        return Media(path, info, cover, thumbnail)

    monkeypatch.setattr(chat, "download", download)
    request = AsyncMock(side_effect=telegram)
    author = '<a href="tg://user?id=42">{}</a>'
    source = '<a href="https://youtu.be/ok">YouTube</a>'
    script = [
        (42, "/start"),
        (-7, "/start"),
        (42, "/saymyname  Ivan228 "),
        (42, "как  смешно youtu.be/ok\n\nда"),  # Delivered, so the original is deleted.
        (-7, "youtu.be/ok"),  # Cached file_id; the nickname belongs to chat 42 only.
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
    assert downloads == ["https://youtu.be/ok", "https://youtu.be/fail"]
    videos = [c.args[1] for c in request.await_args_list if isinstance(c.args[1], SendVideo)]
    uploaded, *cached = videos
    assert isinstance(uploaded.video, FSInputFile) and isinstance(uploaded.thumbnail, FSInputFile)
    assert isinstance(uploaded.cover, FSInputFile)
    assert [(video.video, video.cover) for video in cached] == [("file-1", "cover-1")] * 2
    assert not list(tmp_path.glob("download-*"))


@pytest.mark.parametrize(
    ("title", "channel", "limit", "expected"),
    [
        ("Смешной кот #shorts #cat", "Коты | ", 96, "Смешной кот — Коты"),
        ("#shorts", "", 96, "Интересный контент"),
        (
            "Очень длинное название видео, которое никак не помещается в заголовок подписи целиком",
            "Канал с очень длинным названием для проверки",
            80,
            "Очень длинное название видео, которое никак… — Канал с очень длинным названием…",
        ),
        ("Название", "Канал", 12, "Название"),  # No room for the channel.
    ],
)
def test_caption_header(title: str, channel: str, limit: int, expected: str) -> None:
    assert caption.header(title, channel, limit) == expected


def test_caption_fits_telegram_limit() -> None:
    author = caption.Author("Ivan", None)
    text = "т" * 990
    assert caption.fits(text, author, "YouTube")
    assert not caption.fits(text + "т" * 20, author, "YouTube")
    built = caption.build("Очень длинное название 🎬 " * 20, "", text, author, "YouTube", "x")
    visible = built.replace('<a href="x">', "").replace("</a>", "")
    assert caption.length(visible) <= caption.CAPTION_LIMIT
    assert visible.startswith("Очень длинное") and "…\n\n" + text in visible


@pytest.mark.parametrize(
    ("url", "start"),
    [
        ("youtu.be/x?t=90", 90),
        ("https://www.youtube.com/watch?v=x&t=1m30s", 90),
        ("https://youtube.com/watch?v=x#t=1h2m3s", 3723),
        ("youtu.be/x?t=abc", None),
    ],
)
def test_youtube_start(url: str, start: int | None) -> None:
    link = classify(url)
    assert link and link.start == start


@pytest.mark.parametrize(
    ("url", "label", "downloadable"),
    [
        ("https://www.youtube.com/watch?v=x&list=y", "YouTube/video", True),
        ("youtu.be/x", "YouTube/video", True),
        ("https://m.youtube.com/shorts/x", "YouTube/shorts", True),
        ("https://youtube.com/clip/Ugkx", "YouTube/clip", True),
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
