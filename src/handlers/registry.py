"""Декларативный runtime registry обработчиков."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Pattern, Sequence

from src.handlers.base import BaseHandler
from src.handlers.contracts import ContentType
from src.handlers.resources.Coub import CoubHandler
from src.handlers.resources.Instagram import InstagramHandler
from src.handlers.resources.TikTok import TikTokHandler
from src.handlers.resources.YandexMusic import YandexMusicHandler
from src.handlers.resources.YouTube import YouTubeHandler

HandlerFactory = Callable[[], BaseHandler]

# Явная фиксация source-статусов вне stable runtime-контура.
_NON_RUNTIME_SOURCE_STATUSES: dict[str, str] = {
    "VK": "in_development",
}


@dataclass(frozen=True, slots=True)
class SourceResilienceProfile:
    """
    Явное описание resilience posture для stable runtime source.

    Поля описывают не SLA, а ожидаемую operational модель:
    какие внешние зависимости участвуют, где находятся основные timeout-budget'ы,
    какие retry/fallback path допустимы и какие degrade signals стоит считать значимыми.
    """

    dependency_surfaces: tuple[str, ...]
    timeout_expectations: tuple[str, ...]
    retry_expectations: tuple[str, ...]
    degrade_signals: tuple[str, ...]
    degrade_behavior: str


@dataclass(frozen=True, slots=True)
class HandlerDescriptor:
    """
    Декларативное описание runtime-обработчика.

    Поля:
    - `pattern`: паттерн распознавания URL;
    - `priority`: приоритет выбора (большее значение = выше приоритет);
    - `feature_flags`: runtime-флаги для поэтапного включения;
    - `factory`: фабрика создания handler-экземпляра;
    - `source_name`: имя источника;
    - `supported_content_types`: поддерживаемые `ContentType`.
    - `resilience_profile`: ожидаемый operational posture для внешних зависимостей source-а.
    """

    source_name: str
    pattern: Pattern[str]
    priority: int
    feature_flags: tuple[str, ...]
    factory: HandlerFactory
    supported_content_types: tuple[ContentType, ...]
    resilience_profile: SourceResilienceProfile


@dataclass(frozen=True, slots=True)
class RuntimeHandlerEntry:
    """Связка descriptor + runtime-экземпляр handler-а."""

    descriptor: HandlerDescriptor
    handler: BaseHandler


class HandlerRegistry:
    """Registry descriptor-объектов и фабрик обработчиков."""

    def __init__(self, descriptors: Sequence[HandlerDescriptor]) -> None:
        self._descriptors = tuple(
            sorted(
                descriptors,
                key=lambda item: item.priority,
                reverse=True,
            )
        )

    @property
    def descriptors(self) -> tuple[HandlerDescriptor, ...]:
        """Возвращает descriptors в порядке runtime-приоритета."""
        return self._descriptors

    def create_runtime_entries(self) -> list[RuntimeHandlerEntry]:
        """Создает runtime-экземпляры обработчиков по фабрикам descriptors."""
        entries: list[RuntimeHandlerEntry] = []
        for descriptor in self._descriptors:
            handler = descriptor.factory()
            entries.append(RuntimeHandlerEntry(descriptor=descriptor, handler=handler))
        return entries

    def get_runtime_handler_names(self) -> tuple[str, ...]:
        """Возвращает имена runtime handler-классов для подготовки temp storage."""
        names: list[str] = []
        for descriptor in self._descriptors:
            factory = descriptor.factory
            name = getattr(factory, "__name__", descriptor.source_name)
            names.append(name)
        return tuple(names)


def _default_descriptors() -> tuple[HandlerDescriptor, ...]:
    """
    Возвращает дефолтный runtime-набор descriptor-объектов.

    Важно: новые handlers добавляются декларативно через этот список.

    В intentionally excluded non-runtime зоне:
    - `VK` остается в статусе in_development.
    """
    return (
        HandlerDescriptor(
            source_name="TikTok",
            pattern=TikTokHandler.PATTERN,
            priority=100,
            feature_flags=("runtime_enabled",),
            factory=TikTokHandler,
            supported_content_types=(
                ContentType.VIDEO,
                ContentType.PHOTO,
                ContentType.MEDIA_GROUP,
                ContentType.PROFILE,
            ),
            resilience_profile=SourceResilienceProfile(
                dependency_surfaces=(
                    "yt-dlp extraction for video and fallback media paths",
                    "TikWM API for photo/slideshow posts",
                    "direct TikTok profile fetches",
                ),
                timeout_expectations=(
                    "TikWM API requests are bounded to 20 seconds",
                    "TikTok profile fetches are bounded to 15 seconds",
                    "shared HTTP media downloads stay on the 10-second thumbnail/audio posture",
                ),
                retry_expectations=(
                    "photo/slideshow flow may fall back from TikWM to yt-dlp once",
                    "no unbounded retry loops after anti-bot or payload-shape failures",
                ),
                degrade_signals=(
                    "tiktok_tikwm_unavailable",
                    "tiktok_fallback_to_ytdlp",
                    "tiktok_profile_fetch_failed",
                ),
                degrade_behavior=(
                    "Return None after the bounded fallback chain is exhausted and let "
                    "processing-layer unsupported/failed semantics stay visible."
                ),
            ),
        ),
        HandlerDescriptor(
            source_name="YouTube",
            pattern=YouTubeHandler.PATTERN,
            priority=90,
            feature_flags=("runtime_enabled",),
            factory=YouTubeHandler,
            supported_content_types=(
                ContentType.VIDEO,
                ContentType.SHORTS,
                ContentType.CHANNEL,
                ContentType.PLAYLIST,
            ),
            resilience_profile=SourceResilienceProfile(
                dependency_surfaces=(
                    "yt-dlp metadata and media extraction",
                    "cookie-backed YouTube requests",
                    "shared HTTP downloads for thumbnails and auxiliary assets",
                ),
                timeout_expectations=(
                    "yt-dlp remains the dominant latency budget for extraction paths",
                    "shared HTTP media downloads stay on the 10-second thumbnail/audio posture",
                ),
                retry_expectations=(
                    "shared yt-dlp video path may retry once with format=best when format selection fails",
                    "no repeated retries after cookie-gated or anti-bot failures",
                ),
                degrade_signals=(
                    "youtube_metadata_extract_failed",
                    "youtube_format_fallback",
                    "youtube_cookie_degraded",
                ),
                degrade_behavior=(
                    "Preserve content-type routing intent, but degrade to failed block handling "
                    "instead of masking extraction errors."
                ),
            ),
        ),
        HandlerDescriptor(
            source_name="Instagram",
            pattern=InstagramHandler.PATTERN,
            priority=80,
            feature_flags=("runtime_enabled",),
            factory=InstagramHandler,
            supported_content_types=(
                ContentType.REELS,
                ContentType.MEDIA_GROUP,
                ContentType.STORIES,
                ContentType.PROFILE,
            ),
            resilience_profile=SourceResilienceProfile(
                dependency_surfaces=(
                    "yt-dlp extraction for reels/media/stories",
                    "Instagram web_profile_info fallback",
                    "cookie-sensitive web requests",
                ),
                timeout_expectations=(
                    "web_profile_info fallback is bounded to 12 seconds",
                    "shared HTTP media downloads stay on the 10-second thumbnail/audio posture",
                ),
                retry_expectations=(
                    "profile flow may fall back from yt-dlp metadata to web_profile_info once",
                    "no repeated retries after cookie-gated or anti-bot failures",
                ),
                degrade_signals=(
                    "instagram_metadata_unavailable",
                    "instagram_web_profile_info_failed",
                    "instagram_cookie_degraded",
                ),
                degrade_behavior=(
                    "Prefer explicit fallback to web profile metadata, then return None so the "
                    "processing layer can surface a clear degraded outcome."
                ),
            ),
        ),
        HandlerDescriptor(
            source_name="COUB",
            pattern=CoubHandler.PATTERN,
            priority=70,
            feature_flags=("runtime_enabled",),
            factory=CoubHandler,
            supported_content_types=(ContentType.VIDEO,),
            resilience_profile=SourceResilienceProfile(
                dependency_surfaces=(
                    "COUB metadata and segments APIs",
                    "direct media downloads",
                    "local ffmpeg muxing",
                    "yt-dlp-style fallback extraction",
                ),
                timeout_expectations=(
                    "COUB metadata API requests are bounded to 15 seconds",
                    "direct COUB media downloads are bounded to 90 seconds",
                ),
                retry_expectations=(
                    "bounded fallback across segments/share/ytdlp paths is expected",
                    "mux attempts must remain finite and stop when ffmpeg is unavailable",
                ),
                degrade_signals=(
                    "coub_api_unavailable",
                    "coub_ffmpeg_unavailable",
                    "coub_pipeline_exhausted",
                ),
                degrade_behavior=(
                    "Exhaust bounded source selection and mux attempts, then fail closed with a "
                    "visible processing-layer error instead of silent partial output."
                ),
            ),
        ),
        HandlerDescriptor(
            source_name="Yandex.Music",
            pattern=YandexMusicHandler.PATTERN,
            priority=60,
            feature_flags=("runtime_enabled",),
            factory=YandexMusicHandler,
            supported_content_types=(ContentType.AUDIO,),
            resilience_profile=SourceResilienceProfile(
                dependency_surfaces=(
                    "Yandex Music API client",
                    "direct track download links",
                    "shared HTTP audio and cover downloads",
                ),
                timeout_expectations=(
                    "shared HTTP audio and cover downloads stay on the 10-second posture",
                    "client initialization and metadata fetches must fail fast enough to stay inside handler smoke budgets",
                ),
                retry_expectations=(
                    "track-id extraction may fall back from original URL to resolved URL once",
                    "no blind retries when token, track or direct link are missing",
                ),
                degrade_signals=(
                    "yandex_music_token_missing",
                    "yandex_music_track_not_found",
                    "yandex_music_direct_link_missing",
                ),
                degrade_behavior=(
                    "Fail closed on auth or metadata gaps and let processing-layer failure "
                    "semantics remain explicit to the user."
                ),
            ),
        ),
    )


def _vk_non_runtime_descriptor() -> HandlerDescriptor:
    """Возвращает descriptor VK для явного non-runtime opt-in."""
    from src.handlers.resources.VK import VKHandler

    return HandlerDescriptor(
        source_name="VK",
        pattern=VKHandler.PATTERN,
        priority=50,
        feature_flags=("non_runtime_opt_in", "in_development"),
        factory=VKHandler,
        supported_content_types=(
            ContentType.AUDIO,
            ContentType.PLAYLIST,
        ),
        resilience_profile=SourceResilienceProfile(
            dependency_surfaces=(
                "VK web audio metadata via al_audio endpoints",
                "cookie-sensitive HTML and JSON extraction",
                "direct/HLS audio download with bounded yt-dlp fallback",
            ),
            timeout_expectations=(
                "handler-level network timeouts stay bounded for local smoke workflows",
                "audio download path remains limited by shared HttpFileService size posture",
            ),
            retry_expectations=(
                "best-effort extraction fallbacks are allowed only inside VK module",
                "no unbounded retries after anti-bot/interstitial responses",
            ),
            degrade_signals=(
                "vk_audio_stream_url_not_found",
                "vk_audio_download_failed",
                "vk_badbrowser_interstitial",
            ),
            degrade_behavior=(
                "Remain opt-in and fail closed for unstable extraction paths without promoting VK to stable runtime."
            ),
        ),
    )


_NON_RUNTIME_DESCRIPTOR_BUILDERS: dict[str, Callable[[], HandlerDescriptor]] = {
    "VK": _vk_non_runtime_descriptor,
}


_DEFAULT_HANDLER_REGISTRY: HandlerRegistry | None = None


def get_default_handler_registry() -> HandlerRegistry:
    """Возвращает singleton-реестр runtime handlers."""
    global _DEFAULT_HANDLER_REGISTRY
    if _DEFAULT_HANDLER_REGISTRY is None:
        _DEFAULT_HANDLER_REGISTRY = HandlerRegistry(_default_descriptors())
    return _DEFAULT_HANDLER_REGISTRY


def get_handler_registry_with_non_runtime_sources(source_names: Sequence[str]) -> HandlerRegistry:
    """Возвращает runtime registry c явным opt-in non-runtime sources."""
    normalized_sources = tuple(
        dict.fromkeys(name.strip() for name in source_names if isinstance(name, str) and name.strip())
    )
    unsupported = sorted(
        source_name
        for source_name in normalized_sources
        if source_name not in _NON_RUNTIME_DESCRIPTOR_BUILDERS
    )
    if unsupported:
        raise ValueError(
            f"Unsupported non-runtime source opt-in: {', '.join(unsupported)}"
        )

    descriptors = list(_default_descriptors())
    for source_name in normalized_sources:
        descriptors.append(_NON_RUNTIME_DESCRIPTOR_BUILDERS[source_name]())
    return HandlerRegistry(descriptors)


def get_non_runtime_source_statuses() -> dict[str, str]:
    """Возвращает статусы источников, исключенных из stable runtime."""
    return dict(_NON_RUNTIME_SOURCE_STATUSES)
