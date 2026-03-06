import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from src.handlers.manager import ServiceManager
from src.utils.Emoji import emoji

router = Router()
service_manager = ServiceManager()
logger = logging.getLogger(__name__)


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    user = message.from_user
    user_id = user.id if user else 0
    username = user.username if user and user.username else "unknown"
    logger.info(
        "User %d (@%s) called /help",
        user_id,
        username,
    )
    try:
        sources = []
        for handler in service_manager.handlers:
            name = handler.source_name
            source_emoji = emoji(name)
            sources.append(f"{source_emoji} {name}")
        sources_text = "\n".join(sources)
        help_text = (
            "Кидай ссылку и я дам тебе сочный контент\n"
            "Я хаваю:\n"
            f"{sources_text}"
        )
        await message.answer(help_text)

    except Exception:
        logger.exception("Error in /help command for user %d", user_id)
        await message.answer("Произошла ошибка при формировании списка источников.")
