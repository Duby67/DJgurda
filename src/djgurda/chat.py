"""Per-chat commands and link handling shared by all sources."""

from importlib.metadata import version

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from djgurda.links import classify, extract_links


def create_router() -> Router:
    active: set[int] = set()  # In memory: every chat is paused after a restart.
    router = Router()

    async def is_active(message: Message) -> bool:
        return message.chat.id in active

    @router.message(Command("start"))
    async def start(message: Message) -> None:
        active.add(message.chat.id)
        await message.answer("Бот активен в этом чате")

    @router.message(Command("stop"), is_active)
    async def stop(message: Message) -> None:
        active.discard(message.chat.id)
        await message.answer("Бот приостановлен в этом чате")

    @router.message(Command("status"))
    async def status(message: Message) -> None:
        state = "активен" if message.chat.id in active else "приостановлен"
        await message.answer(f"Бот {state} в этом чате\nВерсия: {version('djgurda')}")

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
