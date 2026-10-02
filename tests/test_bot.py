"""Exercise routing and outgoing messages without contacting Telegram."""

import asyncio
import re
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, call

import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramNetworkError
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
    Chat,
    ChosenInlineResult,
    FSInputFile,
    InlineQuery,
    InlineQueryResultArticle,
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

from djgurda import caption, chat, emoji
from djgurda.bot import create_dispatcher
from djgurda.chat import HELP
from djgurda.media import LONG_DURATION, Info, Job, Media, MediaError
from djgurda.sources import classify
from djgurda.sources.base import Link
from djgurda.storage import Storage

RESTART = (0, "")


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

    monkeypatch.setattr(chat, "fetch", fetch)
    request = AsyncMock(side_effect=telegram)
    author = '<a href="tg://user?id=42">{}</a>'
    source = emoji.html("YouTube") + ' <a href="https://youtu.be/ok">YouTube</a>'
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
        (42, f"{emoji.html('success')} Бот активен в этом чате"),
        (-7, f"{emoji.html('success')} Бот активен в этом чате"),
        (42, "Имя в этом чате: Ivan228"),
        (
            42,
            f"Title &lt;1&gt; — Channel\n\nкак смешно\nда\n\n{author.format('Ivan228')}\n{source}",
        ),
        (42, "DeleteMessage"),
        (-7, f"Title &lt;1&gt; — Channel\n\n{author.format('Test')}\n{source}"),
        (-7, "DeleteMessage"),
        (42, f"Title &lt;1&gt; — Channel\n\n{author.format('Ivan228')}\n{source}"),
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
    monkeypatch.setattr(chat, "fetch", lambda link, target, job: pytest.fail("downloaded"))
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
    def fetch(link: Link, target: Path, job: Job) -> Media:
        job.admit(LONG_DURATION + 1 if "long" in link.url else 60)
        return Media(target / "video.mp4", Info("Title", "Channel", 60, 2, 3))

    monkeypatch.setattr(chat, "fetch", fetch)
    request = AsyncMock(side_effect=telegram)
    user = User(id=42, is_bot=False, first_name="Test")

    def query(update_id: int, text: str) -> Update:
        return Update(
            update_id=update_id,
            inline_query=InlineQuery(id=str(update_id), from_user=user, query=text, offset=""),
        )

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
                query(3, "смотри youtu.be/ok"),  # Cached: sent at once.
                chosen(4, "youtu.be/long"),  # Long videos are refused in inline mode.
            ]:
                await dispatcher.feed_update(bot, update)
            storage.close()

    asyncio.run(scenario())
    methods = [c.args[1] for c in request.await_args_list]
    answers = [m for m in methods if isinstance(m, AnswerInlineQuery)]
    assert [type(result) for answer in answers for result in answer.results] == [
        InlineQueryResultArticle,
        InlineQueryResultCachedVideo,
    ]
    uploads = [m for m in methods if isinstance(m, SendVideo)]
    assert [upload.chat_id for upload in uploads] == [-100]
    (edit,) = [m for m in methods if isinstance(m, EditMessageMedia)]
    assert edit.inline_message_id == "inline-2"
    assert isinstance(edit.media, InputMediaVideo)
    assert (edit.media.media, edit.media.cover) == ("file-1", "cover-1")
    assert edit.media.caption and "смотри" in edit.media.caption
    (failure,) = [m for m in methods if isinstance(m, EditMessageText)]
    assert failure.inline_message_id == "inline-4"
    assert f"только видео до {LONG_DURATION // 60} минут" in (failure.text or "")


def test_long_media_has_its_own_lane(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    long_admitted, release = threading.Event(), threading.Event()

    def fetch(link: Link, target: Path, job: Job) -> Media:
        long = "long" in link.url
        job.admit(LONG_DURATION + 1 if long else 60)
        if long:
            long_admitted.set()
            release.wait(5)
        return Media(target / "video.mp4", Info("", "", 1, 2, 3))

    monkeypatch.setattr(chat, "fetch", fetch)
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


def test_slow_download_shows_progress(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chat, "PROGRESS_INTERVAL", 0.05)

    def fetch(link: Link, target: Path, job: Job) -> Media:
        for stage in ("скачивание 50%", "обработка"):
            job.stage = stage
            time.sleep(0.3)
        return Media(target / "video.mp4", Info("", "", 1, 2, 3))

    monkeypatch.setattr(chat, "fetch", fetch)
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
    monkeypatch.setattr(
        chat,
        "fetch",
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

    monkeypatch.setattr(chat, "fetch", fetch)
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
    visible = re.sub(r"<[^>]+>", "", built)
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


def test_audio_delivery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fetch(link: Link, target: Path, job: Job) -> Media:
        path = target / "track.mp3"
        return Media(path, Info("Song", "Artist", duration=1, width=None, height=None))

    monkeypatch.setattr(chat, "fetch", fetch)
    request = AsyncMock(side_effect=telegram)
    track = "https://music.yandex.ru/album/1/track/2"
    run_script(request, tmp_path, [(42, "/start"), (42, f"Слушай <это> {track}"), (42, track)])

    audios = [c.args[1] for c in request.await_args_list if isinstance(c.args[1], SendAudio)]
    assert [(a.title, a.performer, str(a.audio).startswith("file://")) for a in audios] == [
        ("Song", "Artist", True),
        ("Song", "Artist", False),
    ]
    assert audios[1].audio == "audio-1"  # Cached file_id.
    footer = (
        f'<a href="tg://user?id=42">Test</a>\n{emoji.html("Yandex Music")} '
        f'<a href="{track}">Yandex Music</a>'
    )
    assert [audio.caption for audio in audios] == [f"Слушай &lt;это&gt;\n\n{footer}", footer]


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
