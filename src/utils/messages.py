"""
Утилиты для форматирования сообщений и подписей.

Содержит функции для создания подписей к медиа и сообщений об ошибках
с учетом ограничений Telegram и безопасной HTML-разметкой.
"""

import html
import re
from typing import Protocol

from src.config import MAX_CAPTION
from src.handlers.contracts import ContentType, MediaResult
from src.utils.Emoji import emoji, EMOJI_ERROR, EMOJI_VIDEO, EMOJI_ARROW

# Паттерн для поиска хэштегов
HASHTAG_PATTERN = re.compile(r'#\w+')
HTML_ANCHOR_PATTERN = re.compile(
    r'^<a href=(?P<quote>["\'])(?P<href>.*?)(?P=quote)>(?P<text>.*)</a>$',
    re.DOTALL,
)
TITLE_ELIGIBLE_TYPES = frozenset(
    {
        ContentType.VIDEO,
        ContentType.PHOTO,
        ContentType.MEDIA_GROUP,
        ContentType.SHORTS,
        ContentType.REELS,
        ContentType.STORIES,
    }
)


class SourceHandler(Protocol):
    """Протокол для объектов-обработчиков, используемых при форматировании сообщений."""

    source_name: str


def _remove_hashtags(text: str) -> str:
    """
    Удаляет хэштеги из текста и нормализует пробелы.
    
    Аргументы:
        text: Исходный текст с хэштегами
        
    Возвращает:
        Очищенный текст без хэштегов
    """
    cleaned = HASHTAG_PATTERN.sub('', text)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def _truncate_plain_text(text: str, limit: int, *, suffix: str = "...") -> str:
    """Truncates raw text so that its escaped HTML representation fits the limit."""
    if limit <= 0:
        return ""

    escaped_suffix = html.escape(suffix)
    if len(escaped_suffix) >= limit:
        return escaped_suffix[:limit]

    escaped_text = html.escape(text)
    if len(escaped_text) <= limit:
        return escaped_text

    budget = limit - len(escaped_suffix)
    left = 0
    right = len(text)
    best = ""

    while left <= right:
        mid = (left + right) // 2
        candidate = html.escape(text[:mid])
        if len(candidate) <= budget:
            best = candidate
            left = mid + 1
        else:
            right = mid - 1

    if not best:
        return escaped_suffix[:limit]
    return best + escaped_suffix


def _truncate_html_anchor(anchor_html: str, limit: int) -> str:
    """Truncates a simple HTML anchor while keeping the tag structure valid."""
    if limit <= 0:
        return ""

    if len(anchor_html) <= limit:
        return anchor_html

    match = HTML_ANCHOR_PATTERN.match(anchor_html)
    if match is None:
        return ""

    href = html.escape(match.group("href"), quote=True)
    text = html.unescape(match.group("text"))
    prefix = f'<a href="{href}">'
    suffix = "</a>"

    text_limit = limit - len(prefix) - len(suffix)
    if text_limit <= 0:
        return ""

    truncated_text = _truncate_plain_text(text, text_limit)
    if not truncated_text:
        return ""

    candidate = f"{prefix}{truncated_text}{suffix}"
    if len(candidate) <= limit:
        return candidate
    return candidate[:limit]


def _build_safe_title(media_result: MediaResult, source: str) -> str | None:
    """
    Возвращает безопасный заголовок для подписи.

    Для всех источников гарантирует fallback, если после очистки хэштегов
    заголовок пустой или исходный title отсутствует/некорректный.
    """
    fallback_title = f"Контент из {source}" if source else "Контент"

    raw_title = media_result.title
    if not isinstance(raw_title, str):
        return fallback_title

    clean_title = _remove_hashtags(raw_title)
    if clean_title:
        return clean_title

    return fallback_title


def _render_sections(sections: list[str]) -> str:
    """Joins non-empty caption sections with Telegram-friendly spacing."""
    non_empty_sections = [section for section in sections if section]
    return "\n\n".join(non_empty_sections)


def _build_identity_block(
    *,
    user_link_prefix: str,
    user_link_html: str,
    source_prefix: str,
    source_link_html: str,
) -> str:
    """Builds a compact user/source block without an extra blank line between rows."""
    return f"{user_link_prefix}{user_link_html}\n{source_prefix}{source_link_html}"


def _build_title_line(media_result: MediaResult, source: str) -> str | None:
    """Builds the media title line before HTML-safe truncation."""
    if media_result.content_type not in TITLE_ELIGIBLE_TYPES:
        return None

    safe_title_value = _build_safe_title(media_result, source)
    if not safe_title_value:
        return None

    uploader = str(media_result.uploader or "").strip()
    if uploader:
        return f"{EMOJI_VIDEO} {safe_title_value} — {uploader}"
    return f"{EMOJI_VIDEO} {safe_title_value}"


def _fit_caption_sections(
    *,
    context_line: str | None,
    title_line: str | None,
    user_link_prefix: str,
    user_link_html: str,
    source_prefix: str,
    source_link_html: str,
) -> str:
    """Keeps the caption valid by shrinking only text-bearing sections."""
    current_context = context_line
    current_title = title_line
    current_user_link = user_link_html
    current_source_link = source_link_html

    for _ in range(6):
        identity_block = _build_identity_block(
            user_link_prefix=user_link_prefix,
            user_link_html=current_user_link,
            source_prefix=source_prefix,
            source_link_html=current_source_link,
        )
        caption = _render_sections(
            [
                current_context or "",
                current_title or "",
                identity_block,
            ]
        )
        if len(caption) <= MAX_CAPTION:
            return caption

        overflow = len(caption) - MAX_CAPTION

        if current_context:
            if current_title:
                other_sections = _render_sections(
                    [
                        current_title,
                        identity_block,
                    ]
                )
                limit = MAX_CAPTION - len(other_sections) - 2
            else:
                other_sections = _render_sections(
                    [
                        identity_block,
                    ]
                )
                limit = MAX_CAPTION - len(other_sections) - 2

            if limit <= 0:
                current_context = None
                continue

            candidate_context = _truncate_plain_text(html.unescape(current_context), limit)
            if candidate_context != current_context:
                current_context = candidate_context
                continue

        if current_title:
            other_sections = _render_sections(
                [
                    identity_block,
                ]
            )
            limit = MAX_CAPTION - len(other_sections) - 2
            if limit <= 0:
                current_title = None
                continue

            candidate_title = _truncate_plain_text(html.unescape(current_title), limit)
            if candidate_title != current_title:
                current_title = candidate_title
                continue

        user_link_limit = len(current_user_link) - overflow
        truncated_user_link = _truncate_html_anchor(current_user_link, user_link_limit)
        if truncated_user_link != current_user_link:
            current_user_link = truncated_user_link
            continue

        source_link_limit = len(current_source_link) - overflow
        truncated_source_link = _truncate_html_anchor(current_source_link, source_link_limit)
        if truncated_source_link != current_source_link:
            current_source_link = truncated_source_link
            continue

        break

    caption = _render_sections(
        [
            current_context or "",
            current_title or "",
            _build_identity_block(
                user_link_prefix=user_link_prefix,
                user_link_html=current_user_link,
                source_prefix=source_prefix,
                source_link_html=current_source_link,
            ),
        ]
    )
    if len(caption) <= MAX_CAPTION:
        return caption
    return caption[:MAX_CAPTION - 3] + "..."


def build_caption(
    user_context: str,
    media_result: MediaResult,
    user_link: str,
    url: str,
    handler: SourceHandler
) -> str:
    """
    Строит подпись для медиа-контента.
    
    Аргументы:
        user_context: Контекст сообщения пользователя
        media_result: Typed-результат обработки контента
        user_link: HTML-ссылка на пользователя
        url: Исходный URL
        handler: Обработчик контента
        
    Возвращает:
        HTML-подпись с ограничением длины
    """
    source = handler.source_name
    context_line = user_context.strip() if user_context else None
    title_line = _build_title_line(media_result, source)
    source_prefix = f"{emoji(source)} "
    source_link_html = f"<a href='{html.escape(url, quote=True)}'>{html.escape(source)}</a>"

    if context_line:
        context_line = html.escape(context_line)

    user_link_prefix = f"{EMOJI_ARROW} "

    caption = _fit_caption_sections(
        context_line=context_line,
        title_line=title_line,
        user_link_prefix=user_link_prefix,
        user_link_html=user_link,
        source_prefix=source_prefix,
        source_link_html=source_link_html,
    )
    return caption

def build_error(
    error_message: str,
    url: str,
    handler: SourceHandler,
    reason: str | None = None,
) -> str:
    """
    Строит сообщение об ошибке.
    
    Аргументы:
        error_message: Текст ошибки
        url: Проблемный URL
        handler: Обработчик контента
        reason: Краткая причина ошибки
        
    Возвращает:
        HTML-сообщение об ошибке
    """
    source = handler.source_name
    safe_url = html.escape(url, quote=True)
    lines = [f"{EMOJI_ERROR} {html.escape(error_message)}."]
    if reason:
        lines.append(f"Причина: {html.escape(reason)}.")
    lines.append(f"{emoji(source)} <a href='{safe_url}'>{source}</a>")
    return "\n".join(lines)
