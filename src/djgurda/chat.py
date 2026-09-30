"""Per-chat commands and link handling shared by all sources."""

from importlib.metadata import version

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from djgurda.links import SOURCES, classify, extract_links
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


def create_router(storage: Storage) -> Router:
    active = storage.active_chats()  # Cached so paused chats cost no database reads.
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

    @router.message(is_active)
    async def links(message: Message) -> None:
        lines = [
            f"{source.name}: обработка ещё не реализована"
            for source in map(classify, extract_links(message))
            if source
        ]
        if lines:
            await message.reply("\n".join(lines))

    return router
