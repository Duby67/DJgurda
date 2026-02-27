import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

MAX_CAPTION = 1024
MAX_AGE_SECONDS = 3600
PHOTO_SIZE_LIMIT = 10 * 1024 * 1024
VIDEO_SIZE_LIMIT = 50 * 1024 * 1024
AUDIO_SIZE_LIMIT = 50 * 1024 * 1024

PROJECT_ROOT = Path(__file__).parent.parent
if not PROJECT_ROOT:
    raise ValueError("PROJECT_ROOT не определен!")
PROJECT_TEMP_DIR = PROJECT_ROOT/"src"/"data"/"temp_files"

BOT_VERSION = os.getenv("BOT_VERSION")
if not BOT_VERSION:
    raise ValueError("BOT_VERSION не найден в .env!")

ADMIN_ID_STR=os.getenv("ADMIN_ID")
if ADMIN_ID_STR is None:
    raise ValueError("ADMIN_ID не найден в .env файле")
try:
    ADMIN_ID = int(ADMIN_ID_STR)
except ValueError:
    raise ValueError("ADMIN_ID должен быть числом")

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env!")

YANDEX_MUSIC_TOKEN = os.getenv("YANDEX_MUSIC_TOKEN")
if not YANDEX_MUSIC_TOKEN:
    raise ValueError("YANDEX_MUSIC_TOKEN не найден в .env!")

YOUTUBE_COOKIES_PATH  = os.getenv("YOUTUBE_COOKIES_PATH")
if not YOUTUBE_COOKIES_PATH :
    raise ValueError("YOUTUBE_COOKIES_PATH не найден в .env!")
YOUTUBE_COOKIES = PROJECT_ROOT / YOUTUBE_COOKIES_PATH 
if not Path(YOUTUBE_COOKIES).exists():
    raise ValueError("Файл YOUTUBE_COOKIES не найден.")
