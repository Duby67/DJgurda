import os
from dotenv import load_dotenv

load_dotenv()

ADMIN_ID_STR=os.getenv("ADMIN_ID")
if ADMIN_ID_STR is None:
    raise ValueError("ADMIN_ID не найден в .env файле")

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env!")

YANDEX_MUSIC_TOKEN = os.getenv("YANDEX_MUSIC_TOKEN")
if not YANDEX_MUSIC_TOKEN:
    raise ValueError("YANDEX_MUSIC_TOKEN не найден в .env!")

ADMIN_ID = int(ADMIN_ID_STR)