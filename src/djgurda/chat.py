"""Per-chat commands and link handling shared by all sources."""

import asyncio
import logging
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command, CommandObject
from aiogram.types import FSInputFile, Message

from djgurda import caption
from djgurda.links import extract_links, strip_links
from djgurda.media import DOWNLOAD_PREFIX, MediaError, download
from djgurda.sources import SOURCES, classify
from djgurda.sources.base import Link
from djgurda.storage import Storage

HELP = "\n".join(
    [
        "Отправьте ссылку, и бот перенесёт медиа в чат.",
        "Источники: " + ", ".join(source.name for source in SOURCES),
        "",
        "/start — включить бота в чате",
        "/stop — приостановить бота в чате",
        "/status — состояние бота и версия",
        "/saymyname имя — имя в подписях в этом чате; без имени — сбросить",
        "/help — эта справка",
    ]
)
NICKNAME_LIMIT = 32

logger = logging.getLogger(__name__)


def create_router(storage: Storage, work_dir: Path) -> Router:
    active = storage.active_chats()  # Cached so paused chats cost no database reads.
    downloads = asyncio.Semaphore(1)  # One download at a time bounds CPU, memory and disk.
    router = Router()

    async def is_active(message: Message) -> bool:
        return message.chat.id in active

    @router.message(Command("start"))
    async def start(message: Message) -> None:
        storage.set_active(message.chat.id, True)
        active.add(message.chat.id)
        await message.answer("Бот активен в этом чате")

    @router.message(Command("stop"), is_active)
    async def stop(message: Message) -> None:
        storage.set_active(message.chat.id, False)
        active.discard(message.chat.id)
        await message.answer("Бот приостановлен в этом чате")

    @router.message(Command("status"))
    async def status(message: Message) -> None:
        state = "активен" if message.chat.id in active else "приостановлен"
        await message.answer(f"Бот {state} в этом чате\nВерсия: {version('djgurda')}")

    @router.message(Command("help"))
    async def help_(message: Message) -> None:
        await message.answer(HELP)

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

    async def deliver(message: Message, bot: Bot, link: Link, text: str) -> None:
        async with downloads:
            with TemporaryDirectory(dir=work_dir, prefix=DOWNLOAD_PREFIX) as target:
                media = await asyncio.to_thread(download, link.url, Path(target))
                video = message.answer_video(
                    FSInputFile(media.path),
                    caption=caption.build(
                        media.title,
                        media.uploader,
                        text,
                        author(message),
                        link.source.name,
                        link.url,
                    ),
                    parse_mode="HTML",
                    duration=media.duration,
                    width=media.width,
                    height=media.height,
                    supports_streaming=True,
                )
                await bot(video, request_timeout=300)  # Uploads up to 50 MB.

    @router.message(is_active)
    async def links(message: Message, bot: Bot) -> None:
        found = [link for link in map(classify, extract_links(message)) if link]
        text = strip_links(message)
        if not found or not caption.fits(text, author(message), found[0].source.name):
            return  # No supported links, or an article whose text would not survive.
        delivered = 0
        for link in found:
            if not link.downloadable:
                await message.reply(f"{link.label}: обработка ещё не реализована")
                continue
            try:
                await deliver(message, bot, link, text)
                delivered += 1
            except MediaError as error:
                await message.reply(f"{link.label}: {error}")
        if delivered == len(found):
            try:
                await message.delete()
            except (TelegramBadRequest, TelegramForbiddenError) as error:
                logger.warning("Cannot delete the original message; grant delete rights: %s", error)

    return router
