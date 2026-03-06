"""Модуль `info`."""
import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from src.config import BOT_VERSION
from src.utils.Emoji import EMOJI_DJGURDA, EMOJI_VERSION, EMOJI_STARTTIME

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("info"))
async def info_command(message: Message) -> None:
    """Функция `info_command`."""
    user = message.from_user
    user_id = user.id if user else 0
    username = user.username if user and user.username else "unknown"
    logger.info(
        "User %d (@%s) called /info",
        user_id,
        username,
    )
    try:
        bot = message.bot
        start_time = getattr(bot, "start_time", None)
        if start_time:
            await message.answer(
                f"{EMOJI_DJGURDA}Погоняло: DJgurda\n"
                f"{EMOJI_VERSION}Статья: {BOT_VERSION}\n"
                f"{EMOJI_STARTTIME}Заход: от {start_time.strftime('%Y-%m-%d %H:%M:%S')}"
            )
        else:
            logger.warning("start_time not set for bot")
            await message.answer("Время запуска неизвестно.")
    except Exception:
        logger.exception("Error in /info command for user %d", user_id)
        await message.answer("Произошла ошибка при получении информации.")
