import logging

from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

router = Router()
logger = logging.getLogger(__name__)

@router.message(Command("start"))
async def start_command(message: Message) -> None:
    user = message.from_user
    logger.info(
        "User %d (@%s) called /start",
        user.id, user.username or "unknown"
    )
    try:
        await message.answer("Чики-Брики! Отправь ссылку и я все сделаю красиво!")
    except Exception as e:
        logger.exception("Error in /start command for user %d", user.id)
        await message.answer("Произошла ошибка. Попробуйте позже.")