import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

MAX_CAPTION = 1024
MAX_AGE_SECONDS = 3600
PHOTO_SIZE_LIMIT = 10 * 1024 * 1024
VIDEO_SIZE_LIMIT = 50 * 1024 * 1024
AUDIO_SIZE_LIMIT = 50 * 1024 * 1024

DEFAULT_KEY = "DEFAULT"
MEDALS = ["🥇", "🥈", "🥉"]
SOURCE_EMOJI = {
    "DJgurda": {"emoji": "🤖", "custom_id": 5264975008282742838},
    "Version":  {"emoji": "📊", "custom_id": 5265156526485574081},
    "StartTime":  {"emoji": "🕒", "custom_id": 5265082193486583367},
    
    "DEFAULT":  {"emoji": "🔗", "custom_id": 5265144934368844008},
    "ERROR":  {"emoji": "❌", "custom_id": 5265178374984210675},
    "WARNING":  {"emoji": "⚠️", "custom_id": 5264832501267860869},
    "SUCCESS":  {"emoji": "✅", "custom_id": 5264890723844530032}, 
    
    "Arrow": {"emoji": "➡️", "custom_id": 5265014762500037687},
    "TikTok": {"emoji": "🎵", "custom_id": 5262660471881765089},
    "YouTube": {"emoji": "📹", "custom_id": 5263003845927147424},
    "Instagram": {"emoji": "📸", "custom_id": 5264912443494144118},
    "Yandex.Music": {"emoji": "🎧", "custom_id": 5264990513114683176}
}

PROJECT_ROOT = Path(__file__).parent.parent
if not PROJECT_ROOT:
    raise ValueError("PROJECT_ROOT не определен!")
PROJECT_TEMP_DIR = PROJECT_ROOT/"src"/"data"/"temp_files"

DB_PATH = os.getenv("BOT_DB_PATH")
if not DB_PATH:
    raise ValueError("BOT_VERSION не найден в .env!")

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
