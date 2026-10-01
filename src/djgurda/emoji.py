"""Custom emoji from the legacy DJgurda Telegram set."""

EMOJI = {
    "bot": ("🤖", "5264975008282742838"),
    "version": ("📊", "5265156526485574081"),
    "error": ("❌", "5265178374984210675"),
    "warning": ("⚠️", "5264832501267860869"),
    "success": ("✅", "5264890723844530032"),
    "YouTube": ("📹", "5263003845927147424"),
    "TikTok": ("🎵", "5262660471881765089"),
    "Instagram": ("📸", "5264912443494144118"),
    "Yandex Music": ("🎧", "5264990513114683176"),
    "VK": ("🔗", "5265144934368844008"),
    "Coub": ("🔗", "5265144934368844008"),
}


def html(key: str) -> str:
    character, custom_id = EMOJI[key]
    return f'<tg-emoji emoji-id="{custom_id}">{character}</tg-emoji>'


def character(key: str) -> str:
    return EMOJI[key][0]
