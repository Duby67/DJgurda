"""Exercise routing and outgoing messages without contacting Telegram."""

import asyncio
import json
import re
import threading
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, call

import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.methods import (
    AnswerInlineQuery,
    DeleteMessage,
    EditMessageMedia,
    EditMessageText,
    SendAudio,
    SendChatAction,
    SendMessage,
    SendVideo,
    TelegramMethod,
)
from aiogram.types import (
    Audio,
    CallbackQuery,
    Chat,
    ChosenInlineResult,
    FSInputFile,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultCachedVideo,
    InputMediaVideo,
    Message,
    MessageEntity,
    MessageOriginUser,
    PhotoSize,
    Update,
    User,
    Video,
)

from djgurda import chat, emoji
from djgurda.bot import create_dispatcher
from djgurda.chat import HELP
from djgurda.media import LONG_DURATION, Info, Job, Media, MediaError
from djgurda.sources import classify
from djgurda.sources.base import Link
from djgurda.storage import Storage

RESTART = (0, "")


def patch_fetch(monkeypatch: pytest.MonkeyPatch, fetch: Callable[[Link, Path, Job], Media]) -> None:
    async def download(link: Link, target: Path, job: Job) -> Media:
        return await asyncio.to_thread(fetch, link, target, job)

    monkeypatch.setattr(chat, "fetch", download)


@pytest.fixture
def storage(tmp_path: Path) -> Iterator[Storage]:
    storage = Storage(tmp_path / "db.sqlite3")
    yield storage
    storage.close()


def message(
    update_id: int,
    chat_id: int,
    text: str,
    forward_origin: MessageOriginUser | None = None,
    via_bot: User | None = None,
) -> Update:
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
            forward_origin=forward_origin,
            via_bot=via_bot,
        ),
    )


def run_script(bot_request: AsyncMock, work_dir: Path, script: list[tuple[int, str]]) -> None:
    async def deliver() -> None:
        async with Bot(token="123456789:offline-test-token") as bot:
            bot.session.make_request = bot_request  # type: ignore[method-assign]
            storage = Storage(work_dir / "db.sqlite3")
            dispatcher = create_dispatcher([100], storage, work_dir, local_api=True)
            for update_id, item in enumerate(script, 1):
                if item == RESTART:
                    storage.close()
                    storage = Storage(work_dir / "db.sqlite3")
                    dispatcher = create_dispatcher([100], storage, work_dir, local_api=True)
                    continue
                chat_id, text = item
                await dispatcher.feed_update(bot, message(update_id, chat_id, text))
            assert storage.unfinished() == []  # Finished deliveries leave the journal.
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
    if isinstance(method, SendAudio):
        audio = Audio(file_id="audio-1", file_unique_id="a", duration=1)
        return Message(
            message_id=98, date=datetime.now(UTC), chat=Chat(id=1, type="private"), audio=audio
        )
    if isinstance(method, SendVideo):  # The bot caches the returned file_id.
        cover = [PhotoSize(file_id="cover-1", file_unique_id="c", width=4, height=3)]
        video = Video(
            file_id="file-1", file_unique_id="u", width=2, height=3, duration=1, cover=cover
        )
        return Message(
            message_id=99, date=datetime.now(UTC), chat=Chat(id=1, type="private"), video=video
        )
    if isinstance(method, SendMessage):  # Progress status is edited later.
        return Message(
            message_id=97, date=datetime.now(UTC), chat=Chat(id=1, type="private"), text="status"
        )
    return True


def test_chat_lifecycle(tmp_path: Path) -> None:
    request = AsyncMock(return_value=True)
    link = "смотри vk.com/wall-1_2"
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

    status = (
        f"{emoji.html('bot')} Бот {{}} в этом чате\n"
        f"{emoji.html('version')} Версия: {version('djgurda')}"
    )
    assert sent(request) == [
        (42, f"{emoji.html('success')} Бот активен в этом чате"),
        (-7, status.format("приостановлен")),
        (-7, HELP),
        (42, status.format("активен")),
        (42, f"{emoji.html('warning')} VK: обработка ещё не реализована"),
        (42, f"{emoji.html('warning')} Бот приостановлен в этом чате"),
        (42, status.format("приостановлен")),
        (42, f"{emoji.html('success')} Бот активен в этом чате"),
        (42, status.format("активен")),
        (-7, status.format("приостановлен")),
    ]
    methods = [c.args[1] for c in request.await_args_list]
    assert all(
        m.parse_mode == "HTML"
        for m in methods
        if isinstance(m, SendMessage) and "<tg-emoji" in m.text
    )


def test_media_delivery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    downloads = []

    def fetch(link: Link, target: Path, job: Job) -> Media:
        assert target.parent == tmp_path
        url = link.url
        downloads.append(url)
        if "fail" in url:
            raise MediaError("не удалось скачать <private>")
        path, cover, thumbnail = target / "video.mp4", target / "cover.jpg", target / "thumb.jpg"
        info = Info("Title <1>", "Channel", duration=1, width=2, height=3)
        return Media(path, info, cover, thumbnail)

    patch_fetch(monkeypatch, fetch)
    request = AsyncMock(side_effect=telegram)
    script = [
        (42, "/start"),
        (-7, "/start"),
        (42, "как  смешно youtu.be/ok\n\nда"),  # Delivered without a caption; original deleted.
        (-7, "youtu.be/ok"),  # Cached file_id.
        (42, "youtu.be/ok youtu.be/fail youtube.com/playlist?list=1"),  # Original stays.
    ]
    run_script(request, tmp_path, script)

    assert sent(request) == [
        (42, f"{emoji.html('success')} Бот активен в этом чате"),
        (-7, f"{emoji.html('success')} Бот активен в этом чате"),
        (42, "SendVideo"),
        (42, "DeleteMessage"),
        (-7, "SendVideo"),
        (-7, "DeleteMessage"),
        (42, "SendVideo"),
        (42, f"{emoji.html('error')} YouTube/video: не удалось скачать &lt;private&gt;"),
        (42, f"{emoji.html('warning')} YouTube/playlist: обработка ещё не реализована"),
    ]
    assert downloads == ["https://youtu.be/ok", "https://youtu.be/fail"]
    videos = [c.args[1] for c in request.await_args_list if isinstance(c.args[1], SendVideo)]
    uploaded, *cached = videos
    assert str(uploaded.video).startswith("file://") and str(uploaded.video).endswith("/video.mp4")
    assert isinstance(uploaded.thumbnail, FSInputFile)
    assert isinstance(uploaded.cover, FSInputFile)
    assert [(video.video, video.cover) for video in cached] == [("file-1", "cover-1")] * 2
    assert not list(tmp_path.glob("download-*"))


def test_forwarded_delivery_is_ignored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    patch_fetch(monkeypatch, lambda link, target, job: pytest.fail("downloaded"))
    request = AsyncMock(side_effect=telegram)

    async def scenario() -> None:
        async with Bot(token="123456789:offline-test-token") as bot:
            bot.session.make_request = request  # type: ignore[method-assign]
            storage = Storage(tmp_path / "db.sqlite3")
            dispatcher = create_dispatcher([100], storage, tmp_path, local_api=True)
            await dispatcher.feed_update(bot, message(1, 42, "/start"))
            origin = MessageOriginUser(
                date=datetime(2026, 1, 1, tzinfo=UTC),
                sender_user=User(id=bot.id, is_bot=True, first_name="DJgurda"),
            )
            await dispatcher.feed_update(bot, message(2, 42, "Title\n\nyoutu.be/ok", origin))
            # Sent through inline mode into an active chat.
            via = User(id=bot.id, is_bot=True, first_name="DJgurda")
            await dispatcher.feed_update(bot, message(3, 42, "Title\n\nyoutu.be/ok", via_bot=via))
            storage.close()

    asyncio.run(scenario())
    assert sent(request) == [(42, f"{emoji.html('success')} Бот активен в этом чате")]


def test_inline_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chat, "PROGRESS_INTERVAL", 0.05)

    def fetch(link: Link, target: Path, job: Job) -> Media:
        if "broken" in link.url:
            raise MediaError("видео недоступно")
        job.admit(LONG_DURATION + 1 if "long" in link.url else 60)
        if "long" in link.url:
            job.stage = "скачивание 50%"
            time.sleep(0.3)
        return Media(target / "video.mp4", Info("Title", "Channel", 60, 2, 3))

    patch_fetch(monkeypatch, fetch)
    request = AsyncMock(side_effect=telegram)
    user = User(id=42, is_bot=False, first_name="Test")

    def query(update_id: int, text: str, chat_type: str = "private") -> Update:
        inline = InlineQuery(
            id=str(update_id), from_user=user, query=text, offset="", chat_type=chat_type
        )
        return Update(update_id=update_id, inline_query=inline)

    def chosen(update_id: int, text: str) -> Update:
        result = ChosenInlineResult(
            result_id=chat.INLINE_DOWNLOAD,
            from_user=user,
            query=text,
            inline_message_id=f"inline-{update_id}",
        )
        return Update(update_id=update_id, chosen_inline_result=result)

    async def scenario() -> None:
        async with Bot(token="123456789:offline-test-token") as bot:
            bot.session.make_request = request  # type: ignore[method-assign]
            storage = Storage(tmp_path / "db.sqlite3")
            dispatcher = create_dispatcher(
                [100], storage, tmp_path, local_api=True, inline_chat_id=-100
            )
            for update in [
                query(1, "youtu.be/ok смотри"),  # New link: a placeholder.
                chosen(2, "youtu.be/ok смотри"),  # Uploaded, then the placeholder is replaced.
                query(3, "youtu.be/ok", chat_type="group"),  # Groups have the bot itself.
            ]:
                await dispatcher.feed_update(bot, update)
            storage.set_caption(user.id, True)  # Set by /caption in the chat with the bot.
            for update in [
                query(4, "смотри youtu.be/ok"),  # Cached: sent at once.
                chosen(5, "youtu.be/long"),  # Long videos take the long lane and show progress.
                chosen(6, "youtu.be/broken"),  # The placeholder shows the failure.
            ]:
                await dispatcher.feed_update(bot, update)
            storage.close()

    asyncio.run(scenario())
    methods = [c.args[1] for c in request.await_args_list]
    answers = [m for m in methods if isinstance(m, AnswerInlineQuery)]
    assert [result.id for answer in answers for result in answer.results] == [
        chat.INLINE_DOWNLOAD,
        "cached",
        chat.INLINE_REDOWNLOAD,  # In case Telegram cannot send the cached file.
    ]
    refused = answers[1]
    assert refused.button is not None and "личной переписке" in refused.button.text
    # The sender is shown by Telegram as "via bot", so the caption has only the source.
    source = '<tg-spoiler>🔗 <a href="https://youtu.be/ok">Источник</a></tg-spoiler>'
    cached = answers[2].results[0]
    assert isinstance(cached, InlineQueryResultCachedVideo) and cached.caption == source
    uploads = [m for m in methods if isinstance(m, SendVideo)]
    assert [upload.chat_id for upload in uploads] == [-100, -100]
    edits = [m for m in methods if isinstance(m, EditMessageMedia)]
    assert [edit.inline_message_id for edit in edits] == ["inline-2", "inline-5"]
    edit = edits[0]
    assert isinstance(edit.media, InputMediaVideo)
    assert (edit.media.media, edit.media.cover) == ("file-1", "cover-1")
    texts = [(m.inline_message_id, m.text) for m in methods if isinstance(m, EditMessageText)]
    # Telegram rejects custom emoji in inline messages unless the bot has a Fragment username.
    assert texts == [
        ("inline-5", "⏳ YouTube/video: скачивание 50%"),
        ("inline-6", "❌ YouTube/video: видео недоступно"),
    ]
    assert edit.media.caption is None
    assert isinstance(edits[1].media, InputMediaVideo)
    assert edits[1].media.caption is not None and "youtu.be/long" in edits[1].media.caption
    (report,) = [m for m in methods if isinstance(m, SendMessage)]
    assert report.chat_id == -100  # Failures are visible without server logs.
    assert report.text.startswith("❌ YouTube/video (inline): видео недоступно\n")
    assert "MediaError: видео недоступно" in report.text


def test_caption_setting(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    patch_fetch(
        monkeypatch, lambda link, target, job: Media(target / "v.mp4", Info("", "", 1, 2, 3))
    )
    request = AsyncMock(side_effect=telegram)
    sender = User(id=7, is_bot=False, first_name="Анна", username="anna_<b>")

    def press(update_id: int, data: str) -> Update:
        menu = Message(message_id=97, date=datetime.now(UTC), chat=Chat(id=-7, type="group"))
        callback = CallbackQuery(
            id=str(update_id), from_user=sender, chat_instance="c", message=menu, data=data
        )
        return Update(update_id=update_id, callback_query=callback)

    def link(update_id: int, url: str) -> Update:
        update = message(update_id, -7, url)
        assert update.message is not None
        return Update(
            update_id=update_id, message=update.message.model_copy(update={"from_user": sender})
        )

    async def scenario() -> None:
        async with Bot(token="123456789:offline-test-token") as bot:
            bot.session.make_request = request  # type: ignore[method-assign]
            storage = Storage(tmp_path / "db.sqlite3")
            dispatcher = create_dispatcher([100], storage, tmp_path, local_api=True)
            for update in [
                message(1, -7, "/start"),
                link(2, "youtu.be/plain"),  # Captions are off by default.
                message(3, -7, "/caption"),
                press(4, chat.CAPTION_ON),
                press(5, chat.CAPTION_ON),  # A repeated press changes nothing.
                link(6, "youtu.be/ok"),
            ]:
                await dispatcher.feed_update(bot, update)
            storage.close()

    asyncio.run(scenario())
    methods = [c.args[1] for c in request.await_args_list]
    menu = next(m for m in methods if isinstance(m, SendMessage) and "Подпись" in m.text)
    assert "выключена" in menu.text
    assert isinstance(menu.reply_markup, InlineKeyboardMarkup)
    assert menu.reply_markup.inline_keyboard[0][0].callback_data == chat.CAPTION_ON
    (edit,) = [m for m in methods if isinstance(m, EditMessageText)]
    assert "включена" in (edit.text or "")
    assert edit.reply_markup is not None
    assert edit.reply_markup.inline_keyboard[0][0].callback_data == chat.CAPTION_OFF
    plain, captioned = [m for m in methods if isinstance(m, SendVideo)]
    assert plain.caption is None
    # A plain nickname, never a mention: a mention would notify the sender on every video.
    assert captioned.caption == (
        '<tg-spoiler>🔗 <a href="https://youtu.be/ok">Источник</a>\n👤 anna_&lt;b&gt;</tg-spoiler>'
    )
    assert captioned.parse_mode == "HTML"


def test_inline_recovers_from_broken_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    downloads = []

    def fetch(link: Link, target: Path, job: Job) -> Media:
        downloads.append(link.url)
        return Media(target / "video.mp4", Info("Title", "Channel", 60, 2, 3))

    async def bot_api(bot: Bot, method: TelegramMethod[Any], timeout: int | None = None) -> Any:
        if isinstance(method, AnswerInlineQuery) and any(
            getattr(result, "video_file_id", None) == "broken" for result in method.results
        ):
            raise TelegramBadRequest(method=method, message="Bad Request: wrong file identifier")
        return await telegram(bot, method, timeout)

    patch_fetch(monkeypatch, fetch)
    request = AsyncMock(side_effect=bot_api)
    user = User(id=42, is_bot=False, first_name="Test")
    link = classify("youtu.be/ok")
    assert link and link.key
    key = link.key

    async def scenario() -> None:
        async with Bot(token="123456789:offline-test-token") as bot:
            bot.session.make_request = request  # type: ignore[method-assign]
            storage = Storage(tmp_path / "db.sqlite3")
            storage.cache(key, "broken", None, Info("Title", "", 60, 2, 3))
            dispatcher = create_dispatcher(
                [100], storage, tmp_path, local_api=True, inline_chat_id=-100
            )
            inline = InlineQuery(
                id="1", from_user=user, query="youtu.be/ok", offset="", chat_type="sender"
            )
            await dispatcher.feed_update(bot, Update(update_id=1, inline_query=inline))
            assert storage.cached(key) is None  # Telegram rejected it: forgotten.
            storage.cache(key, "stale", None, Info("Title", "", 60, 2, 3))
            # Accepted by Telegram but not sendable: two users pick "download again" at once.
            redownloads = [
                Update(
                    update_id=update_id,
                    chosen_inline_result=ChosenInlineResult(
                        result_id=chat.INLINE_REDOWNLOAD,
                        from_user=user,
                        query="youtu.be/ok",
                        inline_message_id=f"inline-{update_id}",
                    ),
                )
                for update_id in (2, 3)
            ]
            await asyncio.gather(*(dispatcher.feed_update(bot, u) for u in redownloads))
            hit = storage.cached(key)
            assert hit and hit[0] == "file-1"  # Replaced by the new upload.
            storage.close()

    asyncio.run(scenario())
    methods = [c.args[1] for c in request.await_args_list]
    answers = [m for m in methods if isinstance(m, AnswerInlineQuery)]
    assert [[result.id for result in answer.results] for answer in answers] == [
        ["cached", chat.INLINE_REDOWNLOAD],
        [chat.INLINE_DOWNLOAD],
    ]
    assert downloads == ["https://youtu.be/ok"]  # The second reuses the new file.
    edits = [m for m in methods if isinstance(m, EditMessageMedia)]
    assert [edit.media.media for edit in edits] == ["file-1", "file-1"]


@pytest.mark.parametrize(
    ("error", "downloaded"),
    [
        ("Bad Request: wrong file identifier/HTTP URL specified", True),
        ("Bad Request: not enough rights to send videos to the chat", False),
    ],
)
def test_cache_is_forgotten_only_for_file_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: str, downloaded: bool
) -> None:
    downloads = []

    def fetch(link: Link, target: Path, job: Job) -> Media:
        downloads.append(link.url)
        return Media(target / "video.mp4", Info("", "", 1, 2, 3))

    async def bot_api(bot: Bot, method: TelegramMethod[Any], timeout: int | None = None) -> Any:
        if isinstance(method, SendVideo) and method.video == "cached":
            raise TelegramBadRequest(method=method, message=error)
        return await telegram(bot, method, timeout)

    patch_fetch(monkeypatch, fetch)
    link = classify("youtu.be/ok")
    assert link and link.key
    storage = Storage(tmp_path / "db.sqlite3")
    storage.cache(link.key, "cached", None, Info("", "", 1, 2, 3))
    storage.close()
    run_script(AsyncMock(side_effect=bot_api), tmp_path, [(42, "/start"), (42, "youtu.be/ok")])
    storage = Storage(tmp_path / "db.sqlite3")
    hit = storage.cached(link.key)
    storage.close()
    assert bool(downloads) == downloaded
    assert hit and hit[0] == ("file-1" if downloaded else "cached")


def test_deliveries_resume_after_restart(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    downloads = []

    def fetch(link: Link, target: Path, job: Job) -> Media:
        downloads.append(link.url)
        return Media(target / "v.mp4", Info("", "", 1, 2, 3))

    patch_fetch(monkeypatch, fetch)
    request = AsyncMock(side_effect=telegram)
    original = Message(message_id=5, date=datetime.now(UTC), chat=Chat(id=42, type="private"))
    # The first link was delivered before the restart; the second was downloading.
    state = {
        "message": original.model_dump(mode="json", include=chat.MESSAGE_FIELDS),
        "urls": ["youtu.be/second"],
        "failed": False,
        "status": 77,
        "sender": "author",  # Captions were on; the original with the sender is gone.
    }

    async def scenario() -> None:
        async with Bot(token="123456789:offline-test-token") as bot:
            bot.session.make_request = request  # type: ignore[method-assign]
            storage = Storage(tmp_path / "db.sqlite3")
            storage.begin("chat:42:5", json.dumps(state))
            storage.begin(
                "inline:inline-1", json.dumps({"url": "https://youtu.be/ok", "redownload": False})
            )
            # Interrupted again and again: given up, so a crashing video cannot loop.
            for _ in range(chat.ATTEMPTS):
                storage.begin(
                    "inline:inline-2",
                    json.dumps({"url": "https://youtu.be/crash", "redownload": False}),
                )
            dispatcher = create_dispatcher(
                [100], storage, tmp_path, local_api=True, inline_chat_id=-100
            )
            await dispatcher.emit_startup(bot=bot)
            for _ in range(100):
                if not storage.unfinished():
                    break
                await asyncio.sleep(0.05)
            assert storage.unfinished() == []
            storage.close()

    asyncio.run(scenario())
    assert downloads == ["https://youtu.be/second", "https://youtu.be/ok"]
    methods = [c.args[1] for c in request.await_args_list]
    deleted = [(m.chat_id, m.message_id) for m in methods if isinstance(m, DeleteMessage)]
    assert deleted == [(42, 77), (42, 5)]  # The stale status, then the delivered original.
    videos = [m for m in methods if isinstance(m, SendVideo)]
    assert [video.chat_id for video in videos] == [42, -100]
    assert "👤 author" in (videos[0].caption or "")
    (edit,) = [m for m in methods if isinstance(m, EditMessageMedia)]
    assert edit.inline_message_id == "inline-1"
    (failure,) = [m for m in methods if isinstance(m, EditMessageText)]
    assert failure.inline_message_id == "inline-2"
    assert failure.text == f"❌ YouTube/video: {chat.INTERRUPTED}"


def test_long_media_has_its_own_lane(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    long_admitted, release = threading.Event(), threading.Event()

    def fetch(link: Link, target: Path, job: Job) -> Media:
        long = "long" in link.url
        job.admit(LONG_DURATION + 1 if long else 60)
        if long:
            long_admitted.set()
            release.wait(5)
        return Media(target / "video.mp4", Info("", "", 1, 2, 3))

    patch_fetch(monkeypatch, fetch)
    request = AsyncMock(side_effect=telegram)

    async def scenario() -> None:
        async with Bot(token="123456789:offline-test-token") as bot:
            bot.session.make_request = request  # type: ignore[method-assign]
            storage = Storage(tmp_path / "db.sqlite3")
            dispatcher = create_dispatcher([100], storage, tmp_path, local_api=True)
            await dispatcher.feed_update(bot, message(1, 42, "/start"))
            first = asyncio.create_task(
                dispatcher.feed_update(bot, message(2, 42, "youtu.be/long1"))
            )
            assert await asyncio.to_thread(long_admitted.wait, 5)
            # While the long download runs, another long one is refused and a short one passes.
            await dispatcher.feed_update(bot, message(3, 42, "youtu.be/long2"))
            await dispatcher.feed_update(bot, message(4, 42, "youtu.be/short"))
            release.set()
            await first
            storage.close()

    asyncio.run(scenario())
    methods = [c.args[1] for c in request.await_args_list]
    assert [m.message_id for m in methods if isinstance(m, DeleteMessage)] == [4, 2]
    assert any(
        isinstance(m, SendMessage) and "уже скачивается длинное видео" in m.text for m in methods
    )
    timeouts = [
        c.kwargs["timeout"] for c in request.await_args_list if isinstance(c.args[1], SendVideo)
    ]
    assert timeouts == [chat.UPLOAD_TIMEOUT, chat.LONG_UPLOAD_TIMEOUT]


def test_same_link_is_downloaded_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    started, release = threading.Event(), threading.Event()
    downloads = []

    def fetch(link: Link, target: Path, job: Job) -> Media:
        downloads.append(link.url)
        started.set()
        release.wait(5)
        return Media(target / "video.mp4", Info("", "", 1, 2, 3))

    patch_fetch(monkeypatch, fetch)
    request = AsyncMock(side_effect=telegram)

    async def scenario() -> None:
        async with Bot(token="123456789:offline-test-token") as bot:
            bot.session.make_request = request  # type: ignore[method-assign]
            storage = Storage(tmp_path / "db.sqlite3")
            dispatcher = create_dispatcher([100], storage, tmp_path, local_api=True)
            await dispatcher.feed_update(bot, message(1, 42, "/start"))
            await dispatcher.feed_update(bot, message(2, -7, "/start"))
            first = asyncio.create_task(dispatcher.feed_update(bot, message(3, 42, "youtu.be/ok")))
            assert await asyncio.to_thread(started.wait, 5)
            second = asyncio.create_task(dispatcher.feed_update(bot, message(4, -7, "youtu.be/ok")))
            await asyncio.sleep(0.1)  # The second request waits instead of downloading.
            release.set()
            await asyncio.gather(first, second)
            storage.close()

    asyncio.run(scenario())
    assert downloads == ["https://youtu.be/ok"]
    videos = [c.args[1] for c in request.await_args_list if isinstance(c.args[1], SendVideo)]
    assert [(video.chat_id, video.video) for video in videos][1:] == [(-7, "file-1")]


def test_duplicate_queue_is_bounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    entered = asyncio.Event()
    release = asyncio.Event()

    async def fetch(link: Link, target: Path, job: Job) -> Media:
        entered.set()
        await release.wait()
        return Media(target / "v.mp4", Info("", "", 1, 2, 3))

    monkeypatch.setattr(chat, "fetch", fetch)
    request = AsyncMock(side_effect=telegram)

    async def scenario() -> None:
        storage = Storage(tmp_path / "db.sqlite3")
        storage.set_active(42, True)
        async with Bot(token="123456789:offline-test-token") as bot:
            bot.session.make_request = request  # type: ignore[method-assign]
            dispatcher = create_dispatcher([100], storage, tmp_path, local_api=True)
            tasks = [
                asyncio.create_task(dispatcher.feed_update(bot, message(1, 42, "youtu.be/same")))
            ]
            await entered.wait()
            tasks.extend(
                asyncio.create_task(dispatcher.feed_update(bot, message(i, 42, "youtu.be/same")))
                for i in range(2, chat.QUEUE_LIMIT + 4)
            )
            await asyncio.sleep(0.05)
            assert len(storage.unfinished()) == chat.QUEUE_LIMIT
            assert sum(task.done() for task in tasks) == 3
            # A cached link takes no queue place, so a full queue does not refuse it.
            cached = classify("youtu.be/cached")
            assert cached is not None and cached.key is not None
            storage.cache(cached.key, "file-cached", None, Info("", "", 1, 2, 3))
            await dispatcher.feed_update(bot, message(99, 42, "youtu.be/cached"))
            release.set()
            await asyncio.gather(*tasks)
        assert storage.unfinished() == []
        storage.close()

    asyncio.run(scenario())
    assert sum("очередь загрузок заполнена" in text for _, text in sent(request)) == 3
    videos = [c.args[1] for c in request.await_args_list if isinstance(c.args[1], SendVideo)]
    assert "file-cached" in [video.video for video in videos]


@pytest.mark.parametrize(
    ("resuming", "notification_fails"), [(False, False), (True, False), (True, True)]
)
def test_shutdown_preserves_delivery_for_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, resuming: bool, notification_fails: bool
) -> None:
    entered = asyncio.Event()
    cancelled = asyncio.Event()
    release = asyncio.Event()

    async def fetch(link: Link, target: Path, job: Job) -> Media:
        entered.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return Media(target / "v.mp4", Info("", "", 1, 2, 3))

    monkeypatch.setattr(chat, "fetch", fetch)

    async def bot_api(bot: Bot, method: TelegramMethod[Any], timeout: int | None = None) -> Any:
        if notification_fails and isinstance(method, SendMessage) and "Бот выключен" in method.text:
            raise TelegramNetworkError(method=method, message="Shutdown notification failed")
        return await telegram(bot, method, timeout)

    request = AsyncMock(side_effect=bot_api)

    async def shutdown(dispatcher: Any, bot: Bot) -> None:
        if notification_fails:
            with pytest.raises(TelegramNetworkError, match="Shutdown notification failed"):
                await dispatcher.emit_shutdown(bot=bot)
        else:
            await dispatcher.emit_shutdown(bot=bot)

    async def scenario() -> None:
        storage = Storage(tmp_path / "db.sqlite3")
        storage.set_active(42, True)
        update = message(1, 42, "youtu.be/restart")
        assert update.message is not None
        if resuming:
            storage.begin(
                "chat:42:1",
                json.dumps(
                    {
                        "message": update.message.model_dump(
                            mode="json", include=chat.MESSAGE_FIELDS
                        ),
                        "urls": ["https://youtu.be/restart"],
                        "failed": False,
                        "status": None,
                    }
                ),
            )
        async with Bot(token="123456789:offline-test-token") as bot:
            bot.session.make_request = request  # type: ignore[method-assign]
            dispatcher = create_dispatcher([100], storage, tmp_path, local_api=True)
            if resuming:
                await dispatcher.emit_startup(bot=bot)
                task = None
            else:
                task = asyncio.create_task(dispatcher.feed_update(bot, update))
            await entered.wait()
            await shutdown(dispatcher, bot)
            assert cancelled.is_set()
            if task:
                assert task.cancelled()
            assert len(storage.unfinished()) == 1
            assert not list(tmp_path.glob("download-*"))
            release.set()
            dispatcher = create_dispatcher([100], storage, tmp_path, local_api=True)
            await dispatcher.emit_startup(bot=bot)
            for _ in range(100):
                if not storage.unfinished():
                    break
                await asyncio.sleep(0.01)
            assert storage.unfinished() == []
            await shutdown(dispatcher, bot)
        storage.close()

    asyncio.run(scenario())
    assert sum(isinstance(c.args[1], SendVideo) for c in request.await_args_list) == int(
        not resuming
    )
    if resuming:
        assert any(
            isinstance(c.args[1], SendMessage) and chat.INTERRUPTED in c.args[1].text
            for c in request.await_args_list
        )


def test_slow_download_shows_progress(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chat, "PROGRESS_INTERVAL", 0.05)

    def fetch(link: Link, target: Path, job: Job) -> Media:
        for stage in ("скачивание 50%", "обработка"):
            job.stage = stage
            time.sleep(0.3)
        return Media(target / "video.mp4", Info("", "", 1, 2, 3))

    patch_fetch(monkeypatch, fetch)
    request = AsyncMock(side_effect=telegram)

    async def scenario() -> None:
        async with Bot(token="123456789:offline-test-token") as bot:
            bot.session.make_request = request  # type: ignore[method-assign]
            storage = Storage(tmp_path / "db.sqlite3")
            dispatcher = create_dispatcher([100], storage, tmp_path, local_api=False)
            await dispatcher.feed_update(bot, message(1, 42, "/start"))
            await dispatcher.feed_update(bot, message(2, 42, "youtu.be/slow"))
            storage.close()

    asyncio.run(scenario())
    methods = [c.args[1] for c in request.await_args_list]
    status = [m.text for m in methods if isinstance(m, SendMessage) and m.text.startswith("⏳")]
    edits = [m.text for m in methods if isinstance(m, EditMessageText)]
    assert status == ["⏳ YouTube/video: скачивание 50%"]
    assert edits == ["⏳ YouTube/video: обработка"]  # Unchanged stages are not re-sent.
    deleted = [m.message_id for m in methods if isinstance(m, DeleteMessage)]
    assert deleted == [97, 2]  # The status, then the delivered original.
    video = next(m for m in methods if isinstance(m, SendVideo))
    assert isinstance(video.video, FSInputFile)  # The cloud Bot API needs an HTTP upload.


@pytest.mark.parametrize("notification_fails", [False, True])
def test_upload_failure_keeps_original_and_continues(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    notification_fails: bool,
) -> None:
    patch_fetch(
        monkeypatch,
        lambda link, target, job: Media(target / "video.mp4", Info("", "", 1, 2, 3)),
    )
    uploads = 0

    async def request(bot: Bot, method: TelegramMethod[Any], timeout: int | None = None) -> Any:
        nonlocal uploads
        if isinstance(method, SendVideo):
            uploads += 1
            if uploads == 1:
                raise TelegramNetworkError(method=method, message="Request timeout")
        if notification_fails and isinstance(method, SendMessage) and "Telegram" in method.text:
            raise TelegramNetworkError(method=method, message="Reply timeout")
        return await telegram(bot, method, timeout)

    mock = AsyncMock(side_effect=request)
    run_script(mock, tmp_path, [(42, "/start"), (42, "youtu.be/fail youtu.be/ok")])
    methods = [c.args[1] for c in mock.await_args_list]
    assert uploads == 2
    assert not any(isinstance(m, DeleteMessage) for m in methods)
    assert any(
        isinstance(m, SendMessage) and "не удалось отправить медиа" in m.text for m in methods
    )
    assert "TelegramNetworkError" in caplog.text
    assert "source=YouTube/video chat=42 message=2" in caplog.text
    assert ("Cannot notify user" in caplog.text) == notification_fails
    assert not list(tmp_path.glob("download-*"))


def test_unexpected_download_failure_is_visible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def fetch(link: Link, target: Path, job: Job) -> Media:
        raise OSError("Disk full")

    patch_fetch(monkeypatch, fetch)
    request = AsyncMock(side_effect=telegram)
    run_script(request, tmp_path, [(42, "/start"), (42, "youtu.be/fail")])
    assert sent(request)[-1] == (
        42,
        f"{emoji.html('error')} YouTube/video: "
        "не удалось обработать ссылку из-за внутренней ошибки бота",
    )
    assert "OSError: Disk full" in caplog.text
    assert not list(tmp_path.glob("download-*"))


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


def test_audio_delivery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fetch(link: Link, target: Path, job: Job) -> Media:
        path = target / "track.mp3"
        return Media(path, Info("Song", "Artist", duration=1, width=None, height=None))

    patch_fetch(monkeypatch, fetch)
    request = AsyncMock(side_effect=telegram)
    track = "https://music.yandex.ru/album/1/track/2"
    run_script(request, tmp_path, [(42, "/start"), (42, f"Слушай <это> {track}"), (42, track)])

    audios = [c.args[1] for c in request.await_args_list if isinstance(c.args[1], SendAudio)]
    assert [(a.title, a.performer, str(a.audio).startswith("file://")) for a in audios] == [
        ("Song", "Artist", True),
        ("Song", "Artist", False),
    ]
    assert audios[1].audio == "audio-1"  # Cached file_id.
    assert [audio.caption for audio in audios] == [None, None]


@pytest.mark.parametrize(
    ("url", "canonical"),
    [
        (
            "https://www.kkinstagram.com/reel/DdZAYgNib18/?stkn=MTFv",
            "https://www.instagram.com/reel/DdZAYgNib18/",
        ),
        (
            "https://www.instagram.com/reel/DdZAYgNib18/?stkn=MTFv&utm_source=ig",
            "https://www.instagram.com/reel/DdZAYgNib18/",
        ),
        ("m.youtube.com/watch?v=x&si=abc&t=5", "https://m.youtube.com/watch?v=x&t=5"),
        ("https://music.youtube.com/watch?v=x", "https://music.youtube.com/watch?v=x"),
        ("https://www.youtube-nocookie.com/embed/x", "https://www.youtube.com/embed/x"),
        ("https://youtu.be/x?si=abc", "https://youtu.be/x"),
        ("https://vm.vxtiktok.com/ZMabc/", "https://vm.tiktok.com/ZMabc/"),
    ],
)
def test_canonical_links(url: str, canonical: str) -> None:
    link = classify(url)
    assert link and link.url == canonical


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
        ("vm.tiktok.com/ZMabc/", "TikTok/video", True),
        ("https://www.tiktok.com/@user/video/123?is_from_webapp=1", "TikTok/video", True),
        ("https://www.tiktok.com/@user/photo/123", "TikTok/photo", False),
        ("https://www.instagram.com/reel/Dd1/?igsh=x", "Instagram/reel", True),
        ("https://www.kkinstagram.com/reels/Dd1/", "Instagram/reel", True),
        ("https://www.instagram.com/p/Dd1/", "Instagram/post", False),
        ("https://music.yandex.ru/album/1/track/2", "Yandex Music/track", True),
        ("https://music.yandex.com/track/2", "Yandex Music/track", True),
        ("https://music.yandex.ru/album/1", "Yandex Music/album", False),
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
    dispatcher = create_dispatcher([100, 200, 100], storage, tmp_path, local_api=True)
    asyncio.run(dispatcher.emit_startup(bot=bot))
    asyncio.run(dispatcher.emit_shutdown(bot=bot))
    assert bot.send_message.await_args_list == [
        call(chat_id=admin_id, text=text, parse_mode="HTML")
        for text in (
            f"{emoji.html('success')} Бот запущен\n"
            f"{emoji.html('version')} Версия: {version('djgurda')}",
            f"{emoji.html('warning')} Бот выключен",
        )
        for admin_id in (100, 200)
    ]


def test_startup_notification_failure_is_not_ignored(storage: Storage, tmp_path: Path) -> None:
    bot = AsyncMock()
    bot.send_message.side_effect = RuntimeError("Notification failed")
    with pytest.raises(RuntimeError, match="Notification failed"):
        asyncio.run(
            create_dispatcher([100], storage, tmp_path, local_api=True).emit_startup(bot=bot)
        )
