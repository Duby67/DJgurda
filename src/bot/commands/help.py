from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from src.services.manager import ServiceManager
from src.bot.processing.emoji import get_emoji

router = Router()
service_manager = ServiceManager()

@router.message(Command("help"))
async def help_command(message: Message) -> None:
    sources = []
    for handler in service_manager.handlers:
        name = handler.source_name
        emoji = get_emoji(name)
        sources.append(f"{emoji}{name}")
    sources_text = "\n".join(sources)
    help_text = (
        "Кидай ссылку и я дам тебе сочный контент\n"
        "Я хаваю:\n"
        f"{sources_text}"
    )
    await message.answer(help_text)