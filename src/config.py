import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ADMIN_ID_STR=os.getenv("ADMIN_ID")
if ADMIN_ID_STR is None:
    raise ValueError("ADMIN_ID не найден в .env файле")
ADMIN_ID = int(ADMIN_ID_STR)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env!")

YANDEX_MUSIC_TOKEN = os.getenv("YANDEX_MUSIC_TOKEN")
if not YANDEX_MUSIC_TOKEN:
    raise ValueError("YANDEX_MUSIC_TOKEN не найден в .env!")

YOUTUBE_COOKIES = os.getenv("YOUTUBE_COOKIES")
if not YOUTUBE_COOKIES:
    raise ValueError("YOUTUBE_COOKIES не найден в .env!")
if not Path(YOUTUBE_COOKIES).exists():
    raise ValueError("Файл cookies не найден.")

PROJECT_ROOT = Path(__file__).parent.parent
PROJECT_TEMP_DIR = PROJECT_ROOT/"src"/"data"/"temp_files"
if not YOUTUBE_COOKIES:
    raise ValueError("PROJECT_ROOT не определен!")
