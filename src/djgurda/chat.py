"""Per-chat commands and link handling shared by all sources."""

import asyncio
import logging
from html import escape
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory

from aiogram import Bot, F, Router
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from aiogram.filters import Command, CommandObject
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
    InputMediaVideo,
    InputTextMessageContent,
    Message,
    MessageOriginUser,
    User,
)
from aiogram.utils.chat_action import ChatActionSender

from djgurda import caption, emoji
from djgurda.diagnostics import diagnostic, redact
from djgurda.links import extract_links, strip_links
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
        "/saymyname имя — имя в подписях в этом чате; без имени — сбросить",
        "/help — эта справка",
        "",
        "В любом чате, даже без бота: @имя_бота ссылка комментарий",
        f"(только видео до {LONG_DURATION // 60} минут).",
    ]
)
NICKNAME_LIMIT = 32
QUEUE_LIMIT = 5  # Short links waiting or downloading; more are refused instead of piling up.
UPLOAD_TIMEOUT = 5 * 60  # Seconds; the local Bot API forwards the file to Telegram meanwhile.
LONG_UPLOAD_TIMEOUT = 2 * 60 * 60  # 2000 MB at about 2.5 Mbit/s.
PROGRESS_INTERVAL = 10  # Seconds between status edits; quick links finish without one.
INLINE_DOWNLOAD = "download"  # Result id of the placeholder replaced after the download.

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


def parse_query(query: str) -> tuple[Link, str] | None:
    """Return the first downloadable video link of an inline query and the remaining text."""
    words = query.split()
    for index, word in enumerate(words):
        link = classify(word)
        if link and link.downloadable and not link.audio:
            return link, " ".join(words[:index] + words[index + 1 :])
    return None


def inline_author(user: User) -> caption.Author:
    url = f"https://t.me/{user.username}" if user.username else f"tg://user?id={user.id}"
    return caption.Author(user.full_name, url)


def fetch(link: Link, target: Path, job: Job) -> Media:
    return link.source.fetch(link.url, target, job)


async def show_progress(message: Message, bot: Bot, link: Link, job: Job) -> None:
    """Reply with the job stage, edit it when it changes, delete it when cancelled.

    Progress is cosmetic: its failures are logged and never affect delivery.
    """
    status: int | None = None
    shown = ""
    try:
        while True:
            await asyncio.sleep(PROGRESS_INTERVAL)
            text = f"⏳ {link.label}: {job.stage}"
            if text == shown:
                continue
            try:
                if status is None:
                    status = (await message.reply(text)).message_id
                else:
                    await bot.edit_message_text(text, chat_id=message.chat.id, message_id=status)
                shown = text
            except Exception as error:
                logger.warning("Cannot show progress: %s", redact(str(error)))
    finally:
        if status is not None:
            try:
                await bot.delete_message(chat_id=message.chat.id, message_id=status)
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
    long_busy = False
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

    @router.message(Command("saymyname"), is_active)
    async def saymyname(message: Message, command: CommandObject) -> None:
        if message.from_user is None:
            return
        name = " ".join((command.args or "").split())
        if len(name) > NICKNAME_LIMIT:
            await message.reply(f"Имя должно быть не длиннее {NICKNAME_LIMIT} символов")
            return
        storage.set_nickname(message.chat.id, message.from_user.id, name or None)
        await message.reply(f"Имя в этом чате: {name}" if name else "Имя в этом чате сброшено")

    def author(message: Message) -> caption.Author:
        user = message.from_user
        if user is None:  # Anonymous admins and channels post as a chat.
            title = message.sender_chat.title if message.sender_chat else None
            return caption.Author(title or "", None)
        name = storage.nickname(message.chat.id, user.id) or user.full_name
        url = f"https://t.me/{user.username}" if user.username else f"tg://user?id={user.id}"
        return caption.Author(name, url)

    async def send(
        message: Message,
        bot: Bot,
        link: Link,
        text: str,
        info: Info,
        file: str | FSInputFile,
        cover: str | FSInputFile | None = None,
        thumbnail: FSInputFile | None = None,
        timeout: int = UPLOAD_TIMEOUT,
    ) -> Message:
        text = caption.build(
            info.title,
            info.uploader,
            text,
            author(message),
            link.source.name,
            link.url,
            include_header=not link.audio,
        )
        method: SendAudio | SendVideo
        if link.audio:
            method = message.answer_audio(
                file,
                caption=text,
                parse_mode="HTML",
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
                caption=text,
                parse_mode="HTML",
                duration=info.duration,
                width=info.width,
                height=info.height,
                supports_streaming=True,
            )
        return await bot(method, request_timeout=timeout)

    async def deliver(message: Message, bot: Bot, link: Link, text: str) -> None:
        nonlocal pending, long_busy
        hit = storage.cached(link.key) if link.key else None
        if link.key and hit:
            file_id, cover_id, info = hit
            try:
                await send(message, bot, link, text, info, file_id, cover_id)
                return
            except TelegramBadRequest as error:
                logger.warning(
                    "Cached file for %s is unusable, downloading: %s", link.key, redact(str(error))
                )
                storage.forget(link.key)
        if pending >= QUEUE_LIMIT:
            raise MediaError("очередь загрузок заполнена, попробуйте позже")
        pending += 1
        acquired = long = False
        loop = asyncio.get_running_loop()
        progress = None

        async def enter_long_lane() -> None:
            nonlocal pending, long_busy, long
            if long_busy:
                raise MediaError("уже скачивается длинное видео, попробуйте позже")
            long_busy = long = True
            pending -= 1
            downloads.release()

        def admit(duration: int | None) -> None:  # Runs in the download thread.
            if (duration or 0) > LONG_DURATION:
                asyncio.run_coroutine_threadsafe(enter_long_lane(), loop).result()

        job = Job(LOCAL_MAX_BYTES if local_api else CLOUD_MAX_BYTES, admit)

        try:
            async with ChatActionSender(
                bot=bot,
                chat_id=message.chat.id,
                message_thread_id=message.message_thread_id,
                action="upload_voice" if link.audio else "upload_video",
            ):
                progress = asyncio.create_task(show_progress(message, bot, link, job))
                await downloads.acquire()
                acquired = True
                job.stage = "получение данных о видео"
                with TemporaryDirectory(dir=work_dir, prefix=DOWNLOAD_PREFIX) as target:
                    media = await asyncio.to_thread(fetch, link, Path(target), job)
                    job.stage = "отправка в Telegram"
                    sent = await send(
                        message,
                        bot,
                        link,
                        text,
                        media.info,
                        # The local Bot API reads the shared volume instead of an HTTP upload.
                        media.path.resolve().as_uri() if local_api else FSInputFile(media.path),
                        FSInputFile(media.cover) if media.cover else None,
                        FSInputFile(media.thumbnail) if media.thumbnail else None,
                        LONG_UPLOAD_TIMEOUT if long else UPLOAD_TIMEOUT,
                    )
        finally:
            if progress:
                progress.cancel()
                await asyncio.gather(progress, return_exceptions=True)
            if long:
                long_busy = False
            else:
                pending -= 1
                if acquired:
                    downloads.release()
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
        found = [link for link in map(classify, extract_links(message)) if link]
        text = strip_links(message)
        if not found or not caption.fits(text, author(message), found[0].source.name):
            return  # No supported links, or an article whose text would not survive.
        delivered = 0
        for link in found:
            if not link.downloadable:
                await message.reply(
                    f"{emoji.html('warning')} {escape(link.label)}: обработка ещё не реализована",
                    parse_mode="HTML",
                )
                continue
            try:
                await deliver(message, bot, link, text)
                delivered += 1
            except MediaError as error:
                await report_failure(message, link, error, str(error))
            except Exception as error:
                await report_failure(message, link, error, delivery_reason(error))
        if delivered == len(found):
            try:
                await message.delete()
            except TelegramAPIError as error:
                logger.warning("Cannot delete the original message: %s", redact(str(error)))

    async def report_failure(message: Message, link: Link, error: Exception, reason: str) -> None:
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

    @router.inline_query()
    async def inline_query(query: InlineQuery) -> None:
        parsed = parse_query(query.query)
        if parsed is None:
            await query.answer([], cache_time=0, is_personal=True)
            return
        link, text = parsed
        hit = storage.cached(link.key) if link.key else None
        if hit:
            file_id, _, info = hit
            body = caption.build(
                info.title,
                info.uploader,
                text,
                inline_author(query.from_user),
                link.source.name,
                link.url,
            )
            result = InlineQueryResultCachedVideo(
                id="cached",
                video_file_id=file_id,
                title=info.title or link.label,
                description=text or None,
                caption=body,
                parse_mode="HTML",
            )
            await query.answer([result], cache_time=0, is_personal=True)
            return
        if inline_chat_id is None:  # New files need a chat to upload to before the edit.
            button = InlineQueryResultsButton(
                text="Загрузка новых ссылок не настроена", start_parameter="inline"
            )
            await query.answer([], cache_time=0, is_personal=True, button=button)
            return
        placeholder = InlineQueryResultArticle(
            id=INLINE_DOWNLOAD,
            title=f"Скачать и отправить: {link.label}",
            description=text or f"Видео до {LONG_DURATION // 60} минут",
            input_message_content=InputTextMessageContent(
                message_text=f"⏳ {link.label}: скачивание…"
            ),
            # Telegram reports inline_message_id only for messages with a keyboard.
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="Источник", url=link.url)]]
            ),
        )
        await query.answer([placeholder], cache_time=0, is_personal=True)

    @router.chosen_inline_result(F.result_id == INLINE_DOWNLOAD)
    async def inline_download(chosen: ChosenInlineResult, bot: Bot) -> None:
        parsed = parse_query(chosen.query)
        message_id = chosen.inline_message_id
        if parsed is None or message_id is None or inline_chat_id is None:
            logger.error("Inline result cannot be processed: no link, message or upload chat")
            return
        link, text = parsed
        try:
            file_id, cover_id, info = await upload_inline(bot, link, inline_chat_id)
            body = caption.build(
                info.title,
                info.uploader,
                text,
                inline_author(chosen.from_user),
                link.source.name,
                link.url,
            )
            media = InputMediaVideo(
                media=file_id,
                cover=cover_id,
                start_timestamp=link.start,
                caption=body,
                parse_mode="HTML",
                duration=info.duration,
                width=info.width,
                height=info.height,
                supports_streaming=True,
            )
            await bot.edit_message_media(media=media, inline_message_id=message_id)
        except Exception as error:
            reason = str(error) if isinstance(error, MediaError) else delivery_reason(error)
            logger.error(
                "Inline delivery failed source=%s reason=%s\n%s",
                link.label,
                reason,
                diagnostic(error),
            )
            try:
                await bot.edit_message_text(
                    f"{emoji.html('error')} {escape(link.label)}: {escape(reason)}",
                    inline_message_id=message_id,
                    parse_mode="HTML",
                )
            except Exception as notification_error:
                logger.error("Cannot show inline failure\n%s", diagnostic(notification_error))

    async def upload_inline(bot: Bot, link: Link, chat_id: int) -> tuple[str, str | None, Info]:
        """Download a short video and upload it to the upload chat for its file_id."""
        nonlocal pending
        hit = storage.cached(link.key) if link.key else None
        if hit:  # Another inline or chat delivery finished first.
            return hit
        if pending >= QUEUE_LIMIT:
            raise MediaError("очередь загрузок заполнена, попробуйте позже")

        def admit(duration: int | None) -> None:  # Runs in the download thread.
            if (duration or 0) > LONG_DURATION:
                raise MediaError(
                    f"через @-упоминание — только видео до {LONG_DURATION // 60} минут"
                )

        job = Job(LOCAL_MAX_BYTES if local_api else CLOUD_MAX_BYTES, admit)
        pending += 1
        try:
            async with downloads:
                with TemporaryDirectory(dir=work_dir, prefix=DOWNLOAD_PREFIX) as target:
                    media = await asyncio.to_thread(fetch, link, Path(target), job)
                    sent = await bot.send_video(
                        chat_id,
                        media.path.resolve().as_uri() if local_api else FSInputFile(media.path),
                        cover=FSInputFile(media.cover) if media.cover else None,
                        thumbnail=FSInputFile(media.thumbnail) if media.thumbnail else None,
                        caption=link.url,
                        duration=media.info.duration,
                        width=media.info.width,
                        height=media.info.height,
                        supports_streaming=True,
                        disable_notification=True,
                        request_timeout=UPLOAD_TIMEOUT,
                    )
        finally:
            pending -= 1
        if sent.video is None:
            raise MediaError("Telegram не вернул загруженное видео")
        covers = sent.video.cover
        cover_id = covers[-1].file_id if covers else None
        if link.key:
            storage.cache(link.key, sent.video.file_id, cover_id, media.info)
        return sent.video.file_id, cover_id, media.info

    return router
