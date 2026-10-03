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


def comment(message: Message) -> str:
    """The message text without its bare links: what the sender wrote about them."""
    text = message.text or message.caption or ""
    entities = message.entities or message.caption_entities or []
    for link in [entity.extract_from(text) for entity in entities if entity.type == "url"]:
        text = text.replace(link, " ")
    return " ".join(text.split())
