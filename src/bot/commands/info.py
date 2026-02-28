import logging

from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from src.config import BOT_VERSION
from src.bot.processing.emoji import EMOJI_DJGURDA, EMOJI_VERSION, EMOJI_STARTTIME

router = Router()
logger = logging.getLogger(__name__)

@router.message(Command("info"))
async def status_command(message: Message):
    user = message.from_user
    logger.info(
        "User %d (@%s) called /info",
        user.id, user.username or "unknown"
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
    except Exception as e:
        logger.exception("Error in /info command for user %d", user.id)
        await message.answer("Произошла ошибка при получении информации.")