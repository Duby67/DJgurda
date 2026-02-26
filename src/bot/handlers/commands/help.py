from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

#from src.bot.handlers.sources import handlers 

router = Router()

@router.message(Command("help"))
async def help_command(message: Message) -> None:
    #sources = [handler.source_name for handler in handlers]
    #sources_text = "\n".join(f"• {source}" for source in sources)
    help_text = (
        "Кидай ссылку и я дам тебе сочный контент\n"
        "Я хаваю:\n"
        #f"{sources_text}"
    )
    await message.answer(help_text)