"""Registry sender-стратегий по `ContentType`."""

from __future__ import annotations

from typing import Awaitable, Callable

from aiogram import types
from aiogram.types import Message
from aiogram.types.input_file import FSInputFile

from src.handlers.contracts import AttachmentKind, AudioAttachment, ContentType, MediaResult

SenderStrategy = Callable[[Message, MediaResult, str], Awaitable[None]]


class SenderRegistry:
    """Декларативный registry для выбора sender-стратегии по типу контента."""

    def __init__(self) -> None:
        self._senders: dict[ContentType, SenderStrategy] = {}

    def register(self, content_type: ContentType, sender: SenderStrategy) -> None:
        """Регистрирует sender-стратегию для конкретного типа контента."""
        self._senders[content_type] = sender

    async def send(self, message: Message, result: MediaResult, caption: str) -> None:
        """Отправляет контент через стратегию, соответствующую `result.content_type`."""
        sender = self._senders.get(result.content_type)
        if sender is None:
            raise ValueError(f"Unsupported content type: {result.content_type.value}")
        await sender(message, result, caption)


async def _send_video_like(message: Message, result: MediaResult, caption: str) -> None:
    if result.main_file_path is None:
        raise ValueError("Video-like content requires main_file_path")

    video = FSInputFile(result.main_file_path)
    thumbnail = None
    if result.thumbnail_path is not None and result.thumbnail_path.exists():
        thumbnail = FSInputFile(result.thumbnail_path)

    await message.answer_video(
        video=video,
        caption=caption,
        thumbnail=thumbnail,
        supports_streaming=True,
    )


async def _send_stories(message: Message, result: MediaResult, caption: str) -> None:
    if result.main_file_path is None:
        raise ValueError("Stories content requires main_file_path")

    if result.story_media_kind == AttachmentKind.PHOTO:
        await message.answer_photo(photo=FSInputFile(result.main_file_path), caption=caption)
        return

    await message.answer_video(
        video=FSInputFile(result.main_file_path),
        caption=caption,
        supports_streaming=True,
    )


async def _send_audio(message: Message, result: MediaResult, caption: str) -> None:
    audio_item = result.audio
    if audio_item is None:
        if result.main_file_path is None:
            raise ValueError("Audio content requires audio payload or main_file_path")
        audio_item = AudioAttachment(
            file_path=result.main_file_path,
            title=result.title,
            performer=result.uploader,
            thumbnail_path=result.thumbnail_path,
        )

    thumbnail = None
    if audio_item.thumbnail_path is not None and audio_item.thumbnail_path.exists():
        thumbnail = FSInputFile(audio_item.thumbnail_path)

    await message.answer_audio(
        audio=FSInputFile(audio_item.file_path),
        title=audio_item.title or result.title or "Audio",
        performer=audio_item.performer or result.uploader or "Unknown",
        thumbnail=thumbnail,
        caption=caption,
    )


async def _send_photo(message: Message, result: MediaResult, caption: str) -> None:
    if result.main_file_path is None:
        raise ValueError("Photo content requires main_file_path")
    await message.answer_photo(photo=FSInputFile(result.main_file_path), caption=caption)


async def _send_media_group(message: Message, result: MediaResult, caption: str) -> None:
    # Сначала отправляем аудио без подписи.
    for audio_item in result.audios:
        thumbnail = None
        if audio_item.thumbnail_path is not None and audio_item.thumbnail_path.exists():
            thumbnail = FSInputFile(audio_item.thumbnail_path)
        await message.answer_audio(
            audio=FSInputFile(audio_item.file_path),
            title=audio_item.title or result.title or "Audio",
            performer=audio_item.performer or result.uploader or "Unknown",
            thumbnail=thumbnail,
            caption=None,
        )

    media: list[types.InputMediaPhoto | types.InputMediaVideo] = []
    for item in result.media_group:
        if item.kind == AttachmentKind.PHOTO:
            media.append(types.InputMediaPhoto(media=FSInputFile(item.file_path)))
        elif item.kind == AttachmentKind.VIDEO:
            media.append(types.InputMediaVideo(media=FSInputFile(item.file_path)))

    if not media:
        return

    if len(media) == 1:
        single = media[0]
        if isinstance(single, types.InputMediaPhoto):
            await message.answer_photo(photo=single.media, caption=caption)
        else:
            await message.answer_video(video=single.media, caption=caption, supports_streaming=True)
        return

    # Telegram поддерживает caption только у элементов группы.
    media[0].caption = caption
    await message.answer_media_group(media=media)


async def _send_profile_or_channel(message: Message, result: MediaResult, caption: str) -> None:
    profile_caption = result.caption_text or caption
    if result.main_file_path is not None and result.main_file_path.exists():
        await message.answer_photo(photo=FSInputFile(result.main_file_path), caption=profile_caption)
        return
    await message.answer(profile_caption)


async def _send_playlist(message: Message, result: MediaResult, caption: str) -> None:
    await message.answer(result.caption_text or caption)


def create_default_sender_registry() -> SenderRegistry:
    """Создает стандартный registry sender-стратегий."""
    registry = SenderRegistry()
    registry.register(ContentType.VIDEO, _send_video_like)
    registry.register(ContentType.SHORTS, _send_video_like)
    registry.register(ContentType.REELS, _send_video_like)
    registry.register(ContentType.STORIES, _send_stories)
    registry.register(ContentType.AUDIO, _send_audio)
    registry.register(ContentType.PHOTO, _send_photo)
    registry.register(ContentType.MEDIA_GROUP, _send_media_group)
    registry.register(ContentType.PROFILE, _send_profile_or_channel)
    registry.register(ContentType.CHANNEL, _send_profile_or_channel)
    registry.register(ContentType.PLAYLIST, _send_playlist)
    return registry


DEFAULT_SENDER_REGISTRY = create_default_sender_registry()
