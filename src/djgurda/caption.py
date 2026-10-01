"""Caption for delivered media, shared by all sources."""

import re
from dataclasses import dataclass
from html import escape

CAPTION_LIMIT = 1024  # Telegram counts visible characters after HTML parsing.
HEADER_LIMIT = 96  # Keeps "title — channel" short so the sender's text stays in front.
CHANNEL_LIMIT = 32
MIN_TITLE = 12  # Below this the channel is dropped to leave room for the title.
PLACEHOLDER = "Интересный контент"
SEPARATOR = " — "
HASHTAG = re.compile(r"#\w+")
EDGE_PUNCTUATION = " -—–|•·,;:"


def length(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


@dataclass(frozen=True)
class Author:
    name: str
    url: str | None


def clean(text: str) -> str:
    """Drop hashtags, extra whitespace and dangling separators."""
    return " ".join(HASHTAG.sub(" ", text).split()).strip(EDGE_PUNCTUATION)


def shorten(text: str, limit: int) -> str:
    """Cut to whole words within `limit`, marking the cut with an ellipsis."""
    if length(text) <= limit:
        return text
    kept = ""
    for word in text.split():
        candidate = f"{kept} {word}".lstrip()
        if length(candidate) + 1 > limit:
            break
        kept = candidate
    if not kept:  # A single word longer than the limit.
        kept = text
        while kept and length(kept) + 1 > limit:
            kept = kept[:-1]
    return kept.rstrip(EDGE_PUNCTUATION) + "…"


def header(title: str, channel: str, limit: int) -> str:
    title = clean(title) or PLACEHOLDER
    channel = shorten(clean(channel), CHANNEL_LIMIT)
    limit = min(limit, HEADER_LIMIT)
    room = limit - length(channel) - length(SEPARATOR)
    if channel and room >= MIN_TITLE:
        return shorten(title, room) + SEPARATOR + channel
    return shorten(title, limit)


def footer_length(author: Author, source: str) -> int:
    return length(author.name) + 1 + length(source)


def fits(text: str, author: Author, source: str) -> bool:
    """Whether the sender's text fits next to a minimal header and the footer."""
    reserved = MIN_TITLE + 2 + footer_length(author, source)
    return (length(text) + 2 if text else 0) + reserved <= CAPTION_LIMIT


def build(
    title: str,
    channel: str,
    text: str,
    author: Author,
    source: str,
    url: str,
    *,
    include_header: bool = True,
) -> str:
    rest = [text] if text else []
    budget = CAPTION_LIMIT - sum(length(part) + 2 for part in rest)
    budget -= footer_length(author, source) + 2
    name = escape(author.name)
    sender = f'<a href="{escape(author.url)}">{name}</a>' if author.url else name
    lines = [escape(header(title, channel, budget))] if include_header else []
    lines += [escape(part) for part in rest]
    lines.append(f'{sender}\n<a href="{escape(url)}">{escape(source)}</a>')
    return "\n\n".join(lines)
