"""Per-chat commands and link handling shared by all sources."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager
from functools import partial
from html import escape
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from aiogram import Bot, F, Router
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from aiogram.filters import Command
from aiogram.methods import SendAudio, SendVideo
from aiogram.types import (
    ChosenInlineResult,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultCachedVideo,
    InlineQueryResultsButton,
    InlineQueryResultUnion,
    InputMediaVideo,
    InputTextMessageContent,
    Message,
    MessageOriginUser,
)
from aiogram.utils.chat_action import ChatActionSender

from djgurda import emoji
from djgurda.diagnostics import diagnostic, redact
from djgurda.downloads import fetch
from djgurda.links import extract_links
from djgurda.media import (
    CLOUD_MAX_BYTES,
    DOWNLOAD_PREFIX,
    LOCAL_MAX_BYTES,
    LONG_DURATION,
    Info,
    Job,
    Media,
    MediaError,
)
from djgurda.sources import SOURCES, classify
from djgurda.sources.base import Link
from djgurda.storage import Storage

HELP = "\n".join(
    [
        "Отправьте ссылку, и бот перенесёт медиа в чат.",
        "Источники: " + ", ".join(f"{emoji.html(source.name)} {source.name}" for source in SOURCES),
        "",
        "/start — включить бота в чате",
        "/stop — приостановить бота в чате",
        "/status — состояние бота и версия",
        "/help — эта справка",
        "",
        "В любом чате, даже без бота: @имя_бота ссылка (только видео).",
    ]
)
QUEUE_LIMIT = 5  # Short links waiting or downloading; more are refused instead of piling up.
# Seconds, as for downloads; the local Bot API forwards the file to Telegram meanwhile.
UPLOAD_TIMEOUT = 2 * 60
LONG_UPLOAD_TIMEOUT = 20 * 60  # 2000 MB at about 14 Mbit/s.
PROGRESS_INTERVAL = 10  # Seconds between status edits; quick links finish without one.
INLINE_DOWNLOAD = "download"  # Result id of the placeholder replaced after the download.
INLINE_REDOWNLOAD = "redownload"  # The same, ignoring a cached file_id Telegram cannot send.
MESSAGE_LIMIT = 4096
ATTEMPTS = 2  # Starts of one delivery, restarts included; guards against a crash loop.
INTERRUPTED = "загрузка прерывалась перезапуском бота, попробуйте снова"
# What a resumed chat delivery needs from the original message: no text and no sender.
MESSAGE_FIELDS: dict[str, Any] = {
    "message_id": True,
    "date": True,
    "chat": {"id", "type"},
    "message_thread_id": True,
    "is_topic_message": True,
    "business_connection_id": True,
}
# Bad Request texts about the chat, message or query rather than the file.
NOT_FILE_ERRORS = (
    "rights",
    "forbidden",
    "chat not found",
    "message to edit not found",
    "message_id_invalid",
    "message is not modified",
    "thread not found",
    "topic",
    "query is too old",
    "query id is invalid",
)

logger = logging.getLogger(__name__)


def delivery_reason(error: Exception) -> str:
    if isinstance(error, TelegramRetryAfter):
        return f"Telegram ограничил отправку, повторите через {error.retry_after} с"
    if isinstance(error, TelegramForbiddenError):
        return "нет прав на отправку в этот чат; проверьте разрешения бота"
    if isinstance(error, TimeoutError):
        return "операция не завершилась вовремя, попробуйте позже"
    if isinstance(error, (TelegramNetworkError, TelegramServerError)):
        return "не удалось отправить медиа: Telegram не ответил или произошёл сбой сети"
    if isinstance(error, TelegramAPIError):
        return "не удалось отправить медиа: Telegram отклонил запрос"
    return "не удалось обработать ссылку из-за внутренней ошибки бота"


def file_rejected(error: Exception) -> bool:
    """Whether Telegram refused the file itself, so its cached file_id must be forgotten.

    Unknown Bad Request texts count as file errors: a needless download costs less than a
    cache entry that never recovers.
    """
    if not isinstance(error, TelegramBadRequest):
        return False
    text = error.message.lower()
    return not any(part in text for part in NOT_FILE_ERRORS)


def parse_query(query: str) -> Link | None:
    """Return the first downloadable video link of an inline query."""
    for word in query.split():
        link = classify(word)
        if link and link.downloadable and not link.audio:
            return link
    return None


async def report_progress(
    link: Link, job: Job, show: Callable[[str], Coroutine[Any, Any, object]]
) -> None:
    """Pass the job stage to `show` when it changes, until cancelled.

    Progress is cosmetic: its failures are logged and never affect delivery.
    """
    shown = ""
    while True:
        await asyncio.sleep(PROGRESS_INTERVAL)
        text = f"⏳ {link.label}: {job.stage}"
        if text == shown:
            continue
        try:
            await show(text)
            shown = text
        except Exception as error:
            logger.warning("Cannot show progress: %s", redact(str(error)))


async def show_progress(
    message: Message,
    bot: Bot,
    link: Link,
    remember: Callable[[int | None], None],
    job: Job,
) -> None:
    """Reply with the job stage, edit it when it changes, delete it when cancelled.

    `remember` keeps the status message id, so a restart can delete a status left behind.
    """
    status: int | None = None

    async def show(text: str) -> None:
        nonlocal status
        if status is None:
            status = (await message.reply(text)).message_id
            remember(status)
        else:
            await bot.edit_message_text(text, chat_id=message.chat.id, message_id=status)

    try:
        await report_progress(link, job, show)
    finally:
        if status is not None:
            try:
                await bot.delete_message(chat_id=message.chat.id, message_id=status)
                remember(None)
            except Exception as error:
                logger.warning("Cannot delete progress: %s", redact(str(error)))


def create_router(
    storage: Storage, work_dir: Path, local_api: bool, inline_chat_id: int | None = None
) -> Router:
    active = storage.active_chats()  # Cached so paused chats cost no database reads.
    # One short and one long download at a time bound CPU, memory and disk. A long one is
    # refused while another is in progress, so it never takes a place in the short queue.
    downloads = asyncio.Semaphore(1)
    pending = 0
    waiting = 0  # Requests waiting for the same media; they share the short queue limit.
    long_busy = False
    running: dict[str, asyncio.Event] = {}  # Media keys being delivered.
    resumed: set[asyncio.Task[None]] = set()  # Keeps the resume task alive.
    router = Router()

    async def is_active(message: Message) -> bool:
        return message.chat.id in active

    @router.message(Command("start"))
    async def start(message: Message) -> None:
        storage.set_active(message.chat.id, True)
        active.add(message.chat.id)
        await message.answer(f"{emoji.html('success')} Бот активен в этом чате", parse_mode="HTML")

    @router.message(Command("stop"), is_active)
    async def stop(message: Message) -> None:
        storage.set_active(message.chat.id, False)
        active.discard(message.chat.id)
        await message.answer(
            f"{emoji.html('warning')} Бот приостановлен в этом чате", parse_mode="HTML"
        )

    @router.message(Command("status"))
    async def status(message: Message) -> None:
        state = "активен" if message.chat.id in active else "приостановлен"
        await message.answer(
            f"{emoji.html('bot')} Бот {state} в этом чате\n"
            f"{emoji.html('version')} Версия: {version('djgurda')}",
            parse_mode="HTML",
        )

    @router.message(Command("help"))
    async def help_(message: Message) -> None:
        await message.answer(HELP, parse_mode="HTML")

    async def send(
        message: Message,
        bot: Bot,
        link: Link,
        info: Info,
        file: str | FSInputFile,
        cover: str | FSInputFile | None = None,
        thumbnail: FSInputFile | None = None,
        timeout: int = UPLOAD_TIMEOUT,
    ) -> Message:
        method: SendAudio | SendVideo
        if link.audio:
            method = message.answer_audio(
                file,
                title=info.title,
                performer=info.uploader,
                duration=info.duration,
                thumbnail=thumbnail,
            )
        else:
            method = message.answer_video(
                file,
                cover=cover,
                thumbnail=thumbnail,
                start_timestamp=link.start,
                duration=info.duration,
                width=info.width,
                height=info.height,
                supports_streaming=True,
            )
        return await bot(method, request_timeout=timeout)

    def upload_file(media: Media) -> str | FSInputFile:
        # The local Bot API reads the shared volume instead of an HTTP upload.
        return media.path.resolve().as_uri() if local_api else FSInputFile(media.path)

    @asynccontextmanager
    async def download_slot(
        link: Link, watch: Callable[[Job], Coroutine[Any, Any, None]] | None = None
    ) -> AsyncIterator[tuple[Media, Job]]:
        """Queue, download and keep the file for the upload inside the block.

        A long video leaves the short queue for its own lane, refused while it is busy.
        """
        nonlocal pending, long_busy
        if pending + waiting >= QUEUE_LIMIT:
            raise MediaError("очередь загрузок заполнена, попробуйте позже")
        pending += 1
        acquired = False
        loop = asyncio.get_running_loop()

        async def enter_long_lane() -> None:
            nonlocal pending, long_busy
            if long_busy:
                raise MediaError("уже скачивается длинное видео, попробуйте позже")
            long_busy = job.long = True
            pending -= 1
            downloads.release()

        def admit(duration: int | None) -> None:  # Runs in the download thread.
            if (duration or 0) > LONG_DURATION:
                asyncio.run_coroutine_threadsafe(enter_long_lane(), loop).result()

        job = Job(LOCAL_MAX_BYTES if local_api else CLOUD_MAX_BYTES, admit)
        progress = asyncio.create_task(watch(job)) if watch else None
        try:
            await downloads.acquire()
            acquired = True
            job.stage = "получение данных о видео"
            with TemporaryDirectory(dir=work_dir, prefix=DOWNLOAD_PREFIX) as target:
                media = await fetch(link, Path(target), job)
                yield media, job
        finally:
            if progress:
                progress.cancel()
                await asyncio.gather(progress, return_exceptions=True)
            if job.long:
                long_busy = False
            else:
                pending -= 1
                if acquired:
                    downloads.release()

    @asynccontextmanager
    async def single_download(link: Link) -> AsyncIterator[None]:
        """Deliver the same media one at a time, so later requests reuse the cached file_id.

        Only a request that must wait takes a queue place; a free cached link is sent at once.
        """
        nonlocal waiting
        key = link.key
        if key is None:
            yield
            return
        if key in running:
            if pending + waiting >= QUEUE_LIMIT:
                raise MediaError("очередь загрузок заполнена, попробуйте позже")
            waiting += 1
            try:
                while event := running.get(key):
                    await event.wait()
            finally:
                waiting -= 1
        running[key] = done = asyncio.Event()
        try:
            yield
        finally:
            del running[key]
            done.set()

    async def deliver(
        message: Message, bot: Bot, link: Link, remember: Callable[[int | None], None]
    ) -> None:
        async with single_download(link):
            hit = storage.cached(link.key) if link.key else None
            if link.key and hit:
                file_id, cover_id, info = hit
                try:
                    await send(message, bot, link, info, file_id, cover_id)
                    return
                except TelegramBadRequest as error:
                    if not file_rejected(error):
                        raise
                    logger.warning(
                        "Cached file for %s is unusable, downloading: %s",
                        link.key,
                        redact(str(error)),
                    )
                    storage.forget(link.key, file_id)
            async with ChatActionSender(
                bot=bot,
                chat_id=message.chat.id,
                message_thread_id=message.message_thread_id,
                action="upload_voice" if link.audio else "upload_video",
            ):
                watch = partial(show_progress, message, bot, link, remember)
                async with download_slot(link, watch) as (media, job):
                    job.stage = "отправка в Telegram"
                    sent = await send(
                        message,
                        bot,
                        link,
                        media.info,
                        upload_file(media),
                        FSInputFile(media.cover) if media.cover else None,
                        FSInputFile(media.thumbnail) if media.thumbnail else None,
                        LONG_UPLOAD_TIMEOUT if job.long else UPLOAD_TIMEOUT,
                    )
            file = sent.audio or sent.video
            if link.key and file:  # Repeated links are resent by file_id without downloading.
                covers = sent.video.cover if sent.video else None
                storage.cache(
                    link.key, file.file_id, covers[-1].file_id if covers else None, media.info
                )

    @router.message(is_active)
    async def links(message: Message, bot: Bot) -> None:
        origin = message.forward_origin
        if isinstance(origin, MessageOriginUser) and origin.sender_user.id == bot.id:
            return  # Our own delivery forwarded from another chat: already processed.
        if message.via_bot and message.via_bot.id == bot.id:
            return  # Sent through our inline mode: already processed.
        urls = [url for url in extract_links(message) if classify(url)]
        if urls:
            await process_message(message, bot, urls, failed=False)

    async def process_message(message: Message, bot: Bot, urls: list[str], failed: bool) -> None:
        """Deliver the links one by one; the original goes once all of them are delivered.

        The journal keeps the links still to deliver, so a restart neither loses nor repeats
        one; it is kept on cancellation, so a shutdown leaves it for the next start.
        """
        delivery_id = f"chat:{message.chat.id}:{message.message_id}"
        state = {
            "message": message.model_dump(mode="json", include=MESSAGE_FIELDS),
            "urls": urls,
            "failed": failed,
            "status": None,
        }
        attempts = storage.begin(delivery_id, json.dumps(state))

        def remember(status: int | None) -> None:
            state["status"] = status
            storage.save(delivery_id, json.dumps(state))

        for index, url in enumerate(urls):
            link = classify(url)
            if link is None:
                raise ValueError(f"Unrecognized link in the delivery journal: {url}")
            if attempts > ATTEMPTS:
                await report_failure(message, bot, link, MediaError(INTERRUPTED), INTERRUPTED)
                failed = True
            elif not link.downloadable:
                await message.reply(
                    f"{emoji.html('warning')} {escape(link.label)}: обработка ещё не реализована",
                    parse_mode="HTML",
                )
                failed = True
            else:
                try:
                    await deliver(message, bot, link, remember)
                except MediaError as error:
                    await report_failure(message, bot, link, error, str(error))
                    failed = True
                except Exception as error:
                    await report_failure(message, bot, link, error, delivery_reason(error))
                    failed = True
            state.update(urls=urls[index + 1 :], failed=failed, status=None)
            storage.save(delivery_id, json.dumps(state))
        if not failed:
            try:
                await message.delete()
            except TelegramAPIError as error:
                logger.warning("Cannot delete the original message: %s", redact(str(error)))
        storage.end(delivery_id)

    async def report_error(bot: Bot, link: Link, reason: str, error: Exception, where: str) -> None:
        """Post a failure to the inline upload chat, where it is seen without server logs."""
        if inline_chat_id is None:
            return
        header = f"❌ {link.label} ({where}): {reason}\n{link.url}\n\n"
        trace = diagnostic(error)[-(MESSAGE_LIMIT - len(header)) :]  # The cause is at the end.
        try:
            await bot.send_message(inline_chat_id, header + trace, disable_notification=True)
        except Exception as failure:
            logger.error("Cannot report the failure\n%s", diagnostic(failure))

    async def report_failure(
        message: Message, bot: Bot, link: Link, error: Exception, reason: str
    ) -> None:
        await report_error(bot, link, reason, error, f"чат {message.chat.id}")
        logger.error(
            "Media delivery failed source=%s chat=%s message=%s reason=%s\n%s",
            link.label,
            message.chat.id,
            message.message_id,
            reason,
            diagnostic(error),
        )
        try:
            await message.reply(
                f"{emoji.html('error')} {escape(link.label)}: {escape(reason)}", parse_mode="HTML"
            )
        except Exception as notification_error:
            logger.error(
                "Cannot notify user source=%s chat=%s message=%s\n%s",
                link.label,
                message.chat.id,
                message.message_id,
                diagnostic(notification_error),
            )

    def placeholder(link: Link, fresh: bool) -> InlineQueryResultArticle:
        return InlineQueryResultArticle(
            id=INLINE_REDOWNLOAD if fresh else INLINE_DOWNLOAD,
            title=f"{'Скачать заново' if fresh else 'Скачать и отправить'}: {link.label}",
            description="Если видео выше не отправляется"
            if fresh
            else "Видео придёт после загрузки",
            input_message_content=InputTextMessageContent(
                message_text=f"⏳ {link.label}: скачивание…"
            ),
            # Telegram reports inline_message_id only for messages with a keyboard.
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="Источник", url=link.url)]]
            ),
        )

    async def answer_inline(
        query: InlineQuery, link: Link, hit: tuple[str, str | None, Info] | None
    ) -> None:
        results: list[InlineQueryResultUnion] = []
        if hit:
            file_id, _, info = hit
            results.append(
                InlineQueryResultCachedVideo(
                    id="cached", video_file_id=file_id, title=info.title or link.label
                )
            )
        if inline_chat_id is not None:  # New files need a chat to upload to before the edit.
            results.append(placeholder(link, fresh=hit is not None))
        button = (
            None
            if results
            else InlineQueryResultsButton(
                text="Загрузка новых ссылок не настроена", start_parameter="inline"
            )
        )
        await query.answer(results, cache_time=0, is_personal=True, button=button)

    @router.inline_query()
    async def inline_query(query: InlineQuery) -> None:
        link = parse_query(query.query)
        if link is None:
            await query.answer([], cache_time=0, is_personal=True)
            return
        hit = storage.cached(link.key) if link.key else None
        try:
            await answer_inline(query, link, hit)
        except TelegramBadRequest as error:
            if not (hit and link.key and file_rejected(error)):
                raise
            logger.warning(
                "Cached file for %s is unusable inline, offering a download: %s",
                link.key,
                redact(str(error)),
            )
            storage.forget(link.key, hit[0])
            await answer_inline(query, link, None)

    @router.chosen_inline_result(F.result_id.in_({INLINE_DOWNLOAD, INLINE_REDOWNLOAD}))
    async def inline_download(chosen: ChosenInlineResult, bot: Bot) -> None:
        link = parse_query(chosen.query)
        message_id = chosen.inline_message_id
        if link is None or message_id is None or inline_chat_id is None:
            logger.error("Inline result cannot be processed: no link, message or upload chat")
            return
        redownload = chosen.result_id == INLINE_REDOWNLOAD
        await deliver_inline(bot, link, inline_chat_id, message_id, redownload)

    @router.startup()
    async def resume(bot: Bot) -> None:
        """Finish deliveries a restart interrupted, one by one so they fit the queue."""
        unfinished = storage.unfinished()
        if unfinished:
            task = asyncio.create_task(resume_all(bot, unfinished))
            resumed.add(task)
            task.add_done_callback(resumed.discard)

    @router.shutdown()
    async def stop_resuming() -> None:
        tasks = list(resumed)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def resume_all(bot: Bot, unfinished: list[tuple[str, str]]) -> None:
        for delivery_id, text in unfinished:
            try:
                await resume_one(bot, delivery_id, json.loads(text))
            except Exception as error:  # One broken record must not block the rest.
                logger.error("Cannot resume %s\n%s", delivery_id, diagnostic(error))
                storage.end(delivery_id)

    async def resume_one(bot: Bot, delivery_id: str, state: dict[str, Any]) -> None:
        if delivery_id.startswith("inline:"):
            link = classify(state["url"])
            if link is None or inline_chat_id is None:
                raise ValueError(f"Inline delivery needs a link and INLINE_CHAT_ID: {link}")
            message_id = delivery_id.removeprefix("inline:")
            await deliver_inline(bot, link, inline_chat_id, message_id, state["redownload"])
            return
        message = Message.model_validate(state["message"]).as_(bot)
        if state["status"] is not None:  # The status of the interrupted download.
            try:
                await bot.delete_message(message.chat.id, state["status"])
            except TelegramAPIError as error:
                logger.warning("Cannot delete progress: %s", redact(str(error)))
        await process_message(message, bot, state["urls"], state["failed"])

    async def deliver_inline(
        bot: Bot, link: Link, chat_id: int, message_id: str, redownload: bool
    ) -> None:
        """Replace the placeholder with the video or an error; a restart resumes it.

        The record is kept on cancellation, so a shutdown leaves it for the next start.
        """
        delivery_id = f"inline:{message_id}"
        attempts = storage.begin(
            delivery_id, json.dumps({"url": link.url, "redownload": redownload})
        )
        show = partial(bot.edit_message_text, inline_message_id=message_id)
        watch = partial(report_progress, link, show=show)
        file_id = None
        try:
            if attempts > ATTEMPTS:
                raise MediaError(INTERRUPTED)
            # The file the user saw and reported as unusable, read before waiting for others.
            hit = storage.cached(link.key) if link.key else None
            stale = hit[0] if hit and redownload else None
            file_id, cover_id, info = await upload_inline(bot, link, chat_id, watch, stale)
            media = InputMediaVideo(
                media=file_id,
                cover=cover_id,
                start_timestamp=link.start,
                duration=info.duration,
                width=info.width,
                height=info.height,
                supports_streaming=True,
            )
            await bot.edit_message_media(media=media, inline_message_id=message_id)
        except Exception as error:
            if link.key and file_id and file_rejected(error):
                storage.forget(link.key, file_id)  # The next attempt downloads it again.
            reason = str(error) if isinstance(error, MediaError) else delivery_reason(error)
            logger.error(
                "Inline delivery failed source=%s reason=%s\n%s",
                link.label,
                reason,
                diagnostic(error),
            )
            await report_error(bot, link, reason, error, "inline")
            try:
                await bot.edit_message_text(
                    f"{emoji.character('error')} {escape(link.label)}: {escape(reason)}",
                    inline_message_id=message_id,
                    parse_mode="HTML",
                )
            except Exception as notification_error:
                logger.error("Cannot show inline failure\n%s", diagnostic(notification_error))
        storage.end(delivery_id)

    async def upload_inline(
        bot: Bot,
        link: Link,
        chat_id: int,
        watch: Callable[[Job], Coroutine[Any, Any, None]],
        stale: str | None,
    ) -> tuple[str, str | None, Info]:
        """Download a video and upload it to the upload chat for its file_id.

        `stale` is a cached file_id the user reported as unusable; it is not reused.
        """
        async with single_download(link):
            if stale and link.key:
                storage.forget(link.key, stale)
            hit = storage.cached(link.key) if link.key else None
            if hit:  # Another inline or chat delivery finished first.
                return hit
            return await upload_new(bot, link, chat_id, watch)

    async def upload_new(
        bot: Bot, link: Link, chat_id: int, watch: Callable[[Job], Coroutine[Any, Any, None]]
    ) -> tuple[str, str | None, Info]:
        async with download_slot(link, watch) as (media, job):
            job.stage = "отправка в Telegram"
            sent = await bot.send_video(
                chat_id,
                upload_file(media),
                cover=FSInputFile(media.cover) if media.cover else None,
                thumbnail=FSInputFile(media.thumbnail) if media.thumbnail else None,
                caption=link.url,
                duration=media.info.duration,
                width=media.info.width,
                height=media.info.height,
                supports_streaming=True,
                disable_notification=True,
                request_timeout=LONG_UPLOAD_TIMEOUT if job.long else UPLOAD_TIMEOUT,
            )
        if sent.video is None:
            raise MediaError("Telegram не вернул загруженное видео")
        covers = sent.video.cover
        cover_id = covers[-1].file_id if covers else None
        if link.key:
            storage.cache(link.key, sent.video.file_id, cover_id, media.info)
        return sent.video.file_id, cover_id, media.info

    return router
