import re

HASHTAG_PATTERN = re.compile(r'#\w+')

def remove_hashtags(text: str) -> str:
    """Удаляет хештеги из текста"""
    cleaned = HASHTAG_PATTERN.sub('', text)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned