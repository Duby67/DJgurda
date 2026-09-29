"""Telegram handlers and dispatcher composition."""

from aiogram import Dispatcher, Router
from aiogram.filters import CommandStart
from aiogram.types import Message


async def say_hello(message: Message) -> None:
    await message.answer("Hello world")


def create_dispatcher() -> Dispatcher:
    router = Router(name="commands")
    router.message.register(say_hello, CommandStart())
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    return dispatcher
