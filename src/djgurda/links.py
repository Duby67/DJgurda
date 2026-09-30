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


def strip_links(message: Message) -> str:
    """Return the message text without visible URLs, one normalized line per paragraph."""
    text = message.text or message.caption or ""
    entities = message.entities or message.caption_entities or []
    data = text.encode("utf-16-le")  # Entity offsets count UTF-16 code units.
    parts, cursor = [], 0
    for entity in sorted(entities, key=lambda entity: entity.offset):
        if entity.type == "url":
            parts.append(data[cursor * 2 : entity.offset * 2])
            cursor = entity.offset + entity.length
    parts.append(data[cursor * 2 :])
    lines = (" ".join(line.split()) for line in b"".join(parts).decode("utf-16-le").splitlines())
    return "\n".join(line for line in lines if line)
