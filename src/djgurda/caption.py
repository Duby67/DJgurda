"""Caption for delivered media, shared by all sources."""

from dataclasses import dataclass
from html import escape

CAPTION_LIMIT = 1024  # Telegram counts visible characters after HTML parsing.


def length(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


@dataclass(frozen=True)
class Author:
    name: str
    url: str | None


def fits(text: str, author: Author, source: str) -> bool:
    """Whether the sender's text fits next to the author and source lines."""
    return length(text) + length(author.name) + length(source) + 6 <= CAPTION_LIMIT


def build(title: str, text: str, author: Author, source: str, url: str) -> str:
    rest = [text] if text else []
    budget = CAPTION_LIMIT - sum(length(part) + 2 for part in rest)
    budget -= length(author.name) + length(source) + 3
    if length(title) > budget:
        title = title[:budget]
        while title and length(title) + 1 > budget:
            title = title[:-1]
        title = title.rstrip() + "…"
    name = escape(author.name)
    sender = f'<a href="{escape(author.url)}">{name}</a>' if author.url else name
    lines = [escape(title)] if title else []
    lines += [escape(part) for part in rest]
    lines.append(f'{sender}\n<a href="{escape(url)}">{escape(source)}</a>')
    return "\n\n".join(lines)
