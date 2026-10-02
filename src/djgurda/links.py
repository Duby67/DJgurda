"""Link extraction from Telegram messages."""

from aiogram.types import Message


def extract_links(message: Message) -> list[str]:
    text = message.text or message.caption or ""
    entities = message.entities or message.caption_entities or []
    links = []
    for entity in entities:
        if entity.type == "url":
            links.append(entity.extract_from(text))
        elif entity.type == "text_link" and entity.url:
            links.append(entity.url)
    return links
