"""
Адаптер legacy `dict[file_info]` -> typed `MediaResult`.

Нужен для эволюционного перехода без массовой миграции всех handlers.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any
from collections.abc import Mapping

from src.handlers.contracts import (
    AttachmentKind,
    AudioAttachment,
    ContentType,
    MediaAttachment,
    MediaResult,
    normalize_cleanup_paths,
)

LegacyFileInfo = Mapping[str, Any]


class LegacyFileInfoAdapter:
    """Преобразует legacy-словарь результата обработчика в typed-контракт."""

    def to_media_result(
        self,
        file_info: LegacyFileInfo,
        *,
        fallback_source_name: str,
        default_original_url: str,
        default_context: str,
    ) -> MediaResult:
        """Конвертирует `file_info` в `MediaResult` с сохранением текущего поведения."""
        content_type_raw = self._as_text(file_info.get("type"))
        if not content_type_raw:
            raise ValueError("Legacy file_info does not contain 'type'")

        content_type = ContentType.from_raw(content_type_raw)
        source_name = self._as_text(file_info.get("source_name")) or fallback_source_name
        original_url = self._as_text(file_info.get("original_url")) or default_original_url
        context = self._as_text(file_info.get("context")) or default_context
        title = self._as_text(file_info.get("title"))
        uploader = self._as_text(file_info.get("uploader"))
        caption_text = self._as_text(file_info.get("caption_text"))

        main_file_path = self._as_path(file_info.get("file_path"))
        thumbnail_path = self._as_path(file_info.get("thumbnail_path"))
        story_media_kind = self._as_attachment_kind(file_info.get("story_media_type"))
        media_group = self._parse_media_group(file_info.get("files"))

        single_audio = self._parse_audio_attachment(
            file_info.get("audio"),
            fallback_title=title,
            fallback_performer=uploader,
        )
        list_audios = self._parse_audios(
            file_info.get("audios"),
            fallback_title=title,
            fallback_performer=uploader,
        )
        audios = list_audios
        if single_audio is not None and not any(item.file_path == single_audio.file_path for item in audios):
            audios = (single_audio, *audios)

        audio = single_audio
        if audio is None and audios:
            audio = audios[0]

        if content_type == ContentType.AUDIO and audio is None and main_file_path is not None:
            audio = AudioAttachment(
                file_path=main_file_path,
                title=title,
                performer=uploader,
                thumbnail_path=thumbnail_path,
            )
            audios = (audio,)

        cleanup_paths = normalize_cleanup_paths(
            (
                *self._extract_cleanup_paths_from_legacy(file_info),
                *(
                    self._iter_audio_paths((audio,)) if audio is not None else ()
                ),
                *self._iter_audio_paths(audios),
                *(item.file_path for item in media_group),
                *(path for path in (main_file_path, thumbnail_path) if path is not None),
            )
        )

        return MediaResult(
            content_type=content_type,
            source_name=source_name,
            original_url=original_url,
            context=context,
            title=title,
            uploader=uploader,
            caption_text=caption_text,
            main_file_path=main_file_path,
            thumbnail_path=thumbnail_path,
            story_media_kind=story_media_kind,
            media_group=media_group,
            audio=audio,
            audios=audios,
            cleanup_paths=cleanup_paths,
        )

    @staticmethod
    def _iter_audio_paths(audios: tuple[AudioAttachment, ...] | tuple[AudioAttachment]) -> tuple[Path, ...]:
        paths: list[Path] = []
        for audio in audios:
            paths.append(audio.file_path)
            if audio.thumbnail_path is not None:
                paths.append(audio.thumbnail_path)
        return tuple(paths)

    @staticmethod
    def _as_text(value: Any) -> str | None:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return None

    @staticmethod
    def _as_path(value: Any) -> Path | None:
        if isinstance(value, Path):
            return value
        if isinstance(value, str):
            stripped = value.strip()
            if stripped:
                return Path(stripped)
        return None

    @staticmethod
    def _as_attachment_kind(value: Any) -> AttachmentKind | None:
        if not isinstance(value, str):
            return None
        try:
            return AttachmentKind.from_raw(value)
        except ValueError:
            return None

    def _parse_media_group(self, raw_files: Any) -> tuple[MediaAttachment, ...]:
        if not isinstance(raw_files, list):
            return ()

        attachments: list[MediaAttachment] = []
        for item in raw_files:
            if not isinstance(item, Mapping):
                continue
            file_path = self._as_path(item.get("file_path"))
            kind_raw = self._as_text(item.get("type"))
            if file_path is None or not kind_raw:
                continue
            try:
                kind = AttachmentKind.from_raw(kind_raw)
            except ValueError:
                continue
            attachments.append(MediaAttachment(kind=kind, file_path=file_path))
        return tuple(attachments)

    def _parse_audio_attachment(
        self,
        raw_audio: Any,
        *,
        fallback_title: str | None,
        fallback_performer: str | None,
    ) -> AudioAttachment | None:
        if not isinstance(raw_audio, Mapping):
            return None

        file_path = self._as_path(raw_audio.get("file_path"))
        if file_path is None:
            return None

        title = self._as_text(raw_audio.get("title")) or fallback_title
        performer = self._as_text(raw_audio.get("performer")) or fallback_performer
        thumbnail_path = self._as_path(raw_audio.get("thumbnail_path"))

        return AudioAttachment(
            file_path=file_path,
            title=title,
            performer=performer,
            thumbnail_path=thumbnail_path,
        )

    def _parse_audios(
        self,
        raw_audios: Any,
        *,
        fallback_title: str | None,
        fallback_performer: str | None,
    ) -> tuple[AudioAttachment, ...]:
        if not isinstance(raw_audios, list):
            return ()

        audios: list[AudioAttachment] = []
        for item in raw_audios:
            parsed = self._parse_audio_attachment(
                item,
                fallback_title=fallback_title,
                fallback_performer=fallback_performer,
            )
            if parsed is not None:
                audios.append(parsed)
        return tuple(audios)

    def _extract_cleanup_paths_from_legacy(self, file_info: LegacyFileInfo) -> tuple[Path, ...]:
        paths: list[Path] = []

        for key in ("file_path", "thumbnail_path"):
            path = self._as_path(file_info.get(key))
            if path is not None:
                paths.append(path)

        raw_files = file_info.get("files")
        if isinstance(raw_files, list):
            for item in raw_files:
                if not isinstance(item, Mapping):
                    continue
                file_path = self._as_path(item.get("file_path"))
                if file_path is not None:
                    paths.append(file_path)

        raw_audio = file_info.get("audio")
        if isinstance(raw_audio, Mapping):
            for key in ("file_path", "thumbnail_path"):
                path = self._as_path(raw_audio.get(key))
                if path is not None:
                    paths.append(path)

        raw_audios = file_info.get("audios")
        if isinstance(raw_audios, list):
            for item in raw_audios:
                if not isinstance(item, Mapping):
                    continue
                for key in ("file_path", "thumbnail_path"):
                    path = self._as_path(item.get(key))
                    if path is not None:
                        paths.append(path)

        raw_cleanup_paths = file_info.get("cleanup_paths")
        if isinstance(raw_cleanup_paths, list):
            for raw_path in raw_cleanup_paths:
                parsed = self._as_path(raw_path)
                if parsed is not None:
                    paths.append(parsed)

        return tuple(paths)


def adapt_handler_output(
    output: Any,
    *,
    fallback_source_name: str,
    default_original_url: str,
    default_context: str,
) -> MediaResult:
    """
    Нормализует выход handler-а в typed `MediaResult`.

    Поддерживает:
    - уже typed `MediaResult`;
    - legacy `dict[file_info]`.
    """
    if isinstance(output, MediaResult):
        source_name = output.source_name or fallback_source_name
        original_url = output.original_url or default_original_url
        context = output.context or default_context
        if (
            source_name != output.source_name
            or original_url != output.original_url
            or context != output.context
        ):
            return replace(
                output,
                source_name=source_name,
                original_url=original_url,
                context=context,
            )
        return output

    if isinstance(output, Mapping):
        adapter = LegacyFileInfoAdapter()
        return adapter.to_media_result(
            output,
            fallback_source_name=fallback_source_name,
            default_original_url=default_original_url,
            default_context=default_context,
        )

    raise TypeError(f"Unsupported handler output type: {type(output)!r}")
