"""
Typed-контракты результата обработчиков.

Модуль фиксирует явную границу между handler-слоем и orchestration-слоем.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping


class ContentType(str, Enum):
    """Поддерживаемые типы контента в runtime-контракте."""

    VIDEO = "video"
    SHORTS = "shorts"
    REELS = "reels"
    STORIES = "stories"
    AUDIO = "audio"
    PHOTO = "photo"
    MEDIA_GROUP = "media_group"
    PROFILE = "profile"
    CHANNEL = "channel"
    PLAYLIST = "playlist"

    @classmethod
    def from_raw(cls, value: str) -> "ContentType":
        """Преобразует строковое значение legacy-типа в enum."""
        return cls(value)


class AttachmentKind(str, Enum):
    """Тип вложения внутри media_group/stories."""

    PHOTO = "photo"
    VIDEO = "video"

    @classmethod
    def from_raw(cls, value: str) -> "AttachmentKind":
        """Преобразует строковое значение в enum типа вложения."""
        return cls(value)


@dataclass(slots=True, frozen=True)
class MediaAttachment:
    """Вложение фото/видео."""

    kind: AttachmentKind
    file_path: Path


@dataclass(slots=True, frozen=True)
class AudioAttachment:
    """Аудио-вложение для одиночного audio и media_group."""

    file_path: Path
    title: str | None = None
    performer: str | None = None
    thumbnail_path: Path | None = None


@dataclass(slots=True, frozen=True)
class MediaResult:
    """
    Единый typed-результат обработчика.

    После адаптации orchestration-слой работает только с этим объектом.
    """

    content_type: ContentType
    source_name: str
    original_url: str
    context: str
    title: str | None = None
    uploader: str | None = None
    caption_text: str | None = None
    main_file_path: Path | None = None
    thumbnail_path: Path | None = None
    story_media_kind: AttachmentKind | None = None
    media_group: tuple[MediaAttachment, ...] = ()
    audio: AudioAttachment | None = None
    audios: tuple[AudioAttachment, ...] = ()
    cleanup_paths: tuple[Path, ...] = ()

    def iter_cleanup_paths(self) -> tuple[Path, ...]:
        """Возвращает дедуплицированный список временных путей для cleanup."""
        candidates: list[Path] = list(self.cleanup_paths)

        if self.main_file_path is not None:
            candidates.append(self.main_file_path)
        if self.thumbnail_path is not None:
            candidates.append(self.thumbnail_path)

        for item in self.media_group:
            candidates.append(item.file_path)

        if self.audio is not None:
            candidates.append(self.audio.file_path)
            if self.audio.thumbnail_path is not None:
                candidates.append(self.audio.thumbnail_path)

        for audio_item in self.audios:
            candidates.append(audio_item.file_path)
            if audio_item.thumbnail_path is not None:
                candidates.append(audio_item.thumbnail_path)

        seen: set[Path] = set()
        ordered_unique: list[Path] = []
        for path in candidates:
            if path in seen:
                continue
            seen.add(path)
            ordered_unique.append(path)
        return tuple(ordered_unique)


LegacyFileInfo = Mapping[str, Any]
HandlerOutput = MediaResult | LegacyFileInfo


def normalize_cleanup_paths(paths: Iterable[Path]) -> tuple[Path, ...]:
    """Дедуплицирует и нормализует список cleanup-путей."""
    seen: set[Path] = set()
    normalized: list[Path] = []
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        normalized.append(path)
    return tuple(normalized)
