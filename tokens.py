import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
YANDEX_MUSIC_TOKEN = os.getenv("YANDEX_MUSIC_TOKEN")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env!")
if not YANDEX_MUSIC_TOKEN:
    raise ValueError("YANDEX_MUSIC_TOKEN не найден в .env!")