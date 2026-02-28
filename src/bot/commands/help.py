import logging

from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from src.handlers.manager import ServiceManager
from src.bot.processing.emoji import get_emoji

router = Router()
service_manager = ServiceManager()
logger = logging.getLogger(__name__)

@router.message(Command("help"))
async def help_command(message: Message) -> None:
    user = message.from_user
    logger.info(
        "User %d (@%s) called /help",
        user.id, user.username or "unknown"
    )
    try:
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
    except Exception as e:
        logger.exception("Error in /help command for user %d", user.id)
        await message.answer("Произошла ошибка при формировании списка источников.")