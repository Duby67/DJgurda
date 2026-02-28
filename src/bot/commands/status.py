from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from src.config import BOT_VERSION
from src.bot.processing.emoji import EMOJI_DJGURDA, EMOJI_VERSION, EMOJI_STARTTIME

router = Router()

@router.message(Command("status"))
async def status_command(message: Message):
    bot = message.bot
    start_time = bot.start_time
    if start_time:
        await message.answer(
            f"{EMOJI_DJGURDA}Погоняло: DJgurda\n"
            f"{EMOJI_VERSION}Статья: {BOT_VERSION}\n"
            f"{EMOJI_STARTTIME}Заход: от {start_time.strftime('%Y-%m-%d %H:%M:%S')}"
        )
    else:
        await message.answer("Время запуска неизвестно.")