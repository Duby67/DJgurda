"""Per-chat commands and link handling shared by all sources."""

import asyncio
import logging
from html import escape
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory

from aiogram import Bot, Router
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
from aiogram.types import FSInputFile, Message
from aiogram.utils.chat_action import ChatActionSender

from djgurda import caption, emoji
from djgurda.diagnostics import diagnostic, redact
from djgurda.links import extract_links, strip_links
from djgurda.media import DOWNLOAD_PREFIX, Info, Media, MediaError
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
    ]
)
NICKNAME_LIMIT = 32
QUEUE_LIMIT = 5  # Links waiting or downloading; more are refused instead of piling up.

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


def fetch(link: Link, target: Path) -> Media:
    return link.source.fetch(link.url, target)


def create_router(storage: Storage, work_dir: Path) -> Router:
    active = storage.active_chats()  # Cached so paused chats cost no database reads.
    downloads = asyncio.Semaphore(1)  # One download at a time bounds CPU, memory and disk.
    pending = 0
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
        return await bot(method, request_timeout=300)  # Uploads up to 50 MB.

    async def deliver(message: Message, bot: Bot, link: Link, text: str) -> None:
        nonlocal pending
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
        try:
            async with (
                downloads,
                ChatActionSender(
                    bot=bot,
                    chat_id=message.chat.id,
                    message_thread_id=message.message_thread_id,
                    action="upload_voice" if link.audio else "upload_video",
                ),
            ):
                with TemporaryDirectory(dir=work_dir, prefix=DOWNLOAD_PREFIX) as target:
                    media = await asyncio.to_thread(fetch, link, Path(target))
                    sent = await send(
                        message,
                        bot,
                        link,
                        text,
                        media.info,
                        FSInputFile(media.path),
                        FSInputFile(media.cover) if media.cover else None,
                        FSInputFile(media.thumbnail) if media.thumbnail else None,
                    )
        finally:
            pending -= 1
        file = sent.audio or sent.video
        if link.key and file:  # Repeated links are resent by file_id without downloading.
            covers = sent.video.cover if sent.video else None
            storage.cache(
                link.key, file.file_id, covers[-1].file_id if covers else None, media.info
            )

    @router.message(is_active)
    async def links(message: Message, bot: Bot) -> None:
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

    return router
