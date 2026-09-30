"""Per-chat commands and link handling shared by all sources."""

import asyncio
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import FSInputFile, Message

from djgurda.links import extract_links
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
        "/help — эта справка",
    ]
)


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

    async def deliver(message: Message, bot: Bot, link: Link) -> None:
        async with downloads:
            with TemporaryDirectory(dir=work_dir, prefix=DOWNLOAD_PREFIX) as target:
                media = await asyncio.to_thread(download, link.url, Path(target))
                video = message.reply_video(
                    FSInputFile(media.path),
                    caption=media.title[:1024],
                    duration=media.duration,
                    width=media.width,
                    height=media.height,
                    supports_streaming=True,
                )
                await bot(video, request_timeout=300)  # Uploads up to 50 MB.

    @router.message(is_active)
    async def links(message: Message, bot: Bot) -> None:
        for link in filter(None, map(classify, extract_links(message))):
            if not link.downloadable:
                await message.reply(f"{link.label}: обработка ещё не реализована")
                continue
            try:
                await deliver(message, bot, link)
            except MediaError as error:
                await message.reply(f"{link.label}: {error}")

    return router
