"""Набор тестовых URL для локального smoke-теста YouTubeHandler.

Файл служит единым источником правды для тестовых ссылок:
- сюда добавляются/обновляются кейсы для проверки обработчика;
- скрипт `test_youtube_handlers_local.py` читает ссылки только из этого файла.
"""

from __future__ import annotations

from typing import Final

# Кейс: YouTube Shorts.
# Ожидаем, что обработчик вернет type='shorts'.
SHORTS_URL: Final[str] = "https://www.youtube.com/shorts/dmTpIU2f7vY"

# Кейс: YouTube Clip.
# На уровне итогового MediaResult clip отправляется как video-like контент.
CLIP_URL: Final[str] = "https://www.youtube.com/clip/UgkxMds3Y9ZTO-MNrUql234Cu6pwyLb-MW45"

# Кейс: профиль канала YouTube (handle-страница).
# Ожидаем, что обработчик вернет type='channel'.
CHANNEL_PROFILE_URL: Final[str] = "https://www.youtube.com/@planeta_pubertat"

# Кейс: обычное YouTube watch-видео.
# Ожидаем, что обработчик вернет type='video'.
WATCH_VIDEO_URL: Final[str] = "https://www.youtube.com/watch?v=m80GOIy9Co4"

# Кейс: live-стрим YouTube.
# Классифицируется как video, но на runtime-слое допускаем failure из-за
# нестабильности/ограничений live extraction.
LIVE_VIDEO_URL: Final[str] = "https://www.youtube.com/watch?v=0FBiyFpV__g"

# Кейс: short URL YouTube (`youtu.be`).
# Ожидаем, что обработчик вернет type='video'.
YOUTU_BE_VIDEO_URL: Final[str] = "https://youtu.be/lJIrF4YjHfQ?si=ts_vJhmA0M0VR9NV"

# Кейс: YouTube Shorts с query-параметром.
# Ожидаем, что обработчик вернет type='shorts'.
SHORTS_URL_WITH_QUERY: Final[str] = "https://youtube.com/shorts/p3Qgwjl7QfA?is=cO0DzvY4PAjCiKmj"

# Кейс: interstitial-ссылка согласия YouTube, которая должна
# распаковаться обратно в shorts URL.
CONSENT_SHORTS_URL: Final[str] = (
    "https://consent.youtube.com/ml?"
    "continue=https%3A%2F%2Fwww.youtube.com%2Fshorts%2FFTKTL9-hcGw%3Fcbrd%3D1"
    "&gl=NL&hl=nl&cm=2&pc=yt&src=1"
)

# Кейс: interstitial-ссылка согласия YouTube с относительным continue.
# Ожидаем распаковку в абсолютный shorts URL.
CONSENT_SHORTS_RELATIVE_URL: Final[str] = (
    "https://consent.youtube.com/ml?"
    "continue=%2Fshorts%2FFTKTL9-hcGw%3Fcbrd%3D1"
    "&gl=NL&hl=nl&cm=2&pc=yt&src=1"
)

YOUTUBE_TEST_CASES: Final[tuple[dict[str, object], ...]] = (
    {
        "name": "shorts",
        "url": SHORTS_URL,
        "expected_type": "shorts",
        "description": "Короткое вертикальное видео YouTube Shorts.",
        "allow_failure": True,
    },
    {
        "name": "shorts_consent",
        "url": CONSENT_SHORTS_URL,
        "expected_type": "shorts",
        "description": "YouTube consent-ссылка должна распаковываться до shorts.",
        "allow_failure": True,
    },
    {
        "name": "shorts_consent_relative",
        "url": CONSENT_SHORTS_RELATIVE_URL,
        "expected_type": "shorts",
        "description": "YouTube consent-ссылка с относительным continue.",
        "allow_failure": True,
    },
    {
        "name": "clip",
        "url": CLIP_URL,
        "expected_type": "video",
        "description": "YouTube Clip должен отрабатываться как video-like контент.",
        "allow_failure": True,
    },
    {
        "name": "shorts_with_query",
        "url": SHORTS_URL_WITH_QUERY,
        "expected_type": "shorts",
        "description": "YouTube Shorts с query-параметром is.",
        "allow_failure": True,
    },
    {
        "name": "channel_profile",
        "url": CHANNEL_PROFILE_URL,
        "expected_type": "channel",
        "description": "Профиль/страница канала YouTube (@handle).",
    },
    {
        "name": "watch_video",
        "url": WATCH_VIDEO_URL,
        "expected_type": "video",
        "description": "Обычное YouTube watch-видео для smoke-проверки video handler.",
        "allow_failure": True,
    },
    {
        "name": "live_video",
        "url": LIVE_VIDEO_URL,
        "expected_type": "video",
        "description": "YouTube live stream; допустим network/extractor failure.",
        "allow_failure": True,
    },
    {
        "name": "youtu_be_video",
        "url": YOUTU_BE_VIDEO_URL,
        "expected_type": "video",
        "description": "Short URL youtu.be должен проходить через video handler.",
        "allow_failure": True,
    },
)

YOUTUBE_URL_SERVICE_NORMALIZATION_CASES: Final[tuple[dict[str, str], ...]] = (
    {
        "name": "shorts_with_tracking",
        "url": "https://youtube.com/shorts/p3Qgwjl7QfA?is=cO0DzvY4PAjCiKmj&feature=share&pp=ygU",
        "normalized_url": "https://www.youtube.com/shorts/p3Qgwjl7QfA",
    },
    {
        "name": "watch_video_with_tracking",
        "url": "https://www.youtube.com/watch?v=m80GOIy9Co4&feature=share&pp=ygU",
        "normalized_url": "https://www.youtube.com/watch?v=m80GOIy9Co4",
    },
    {
        "name": "youtu_be_video_with_tracking",
        "url": YOUTU_BE_VIDEO_URL,
        "normalized_url": "https://youtu.be/lJIrF4YjHfQ",
    },
    {
        "name": "channel_handle_with_tracking",
        "url": "https://youtube.com/@planeta_pubertat?feature=share",
        "normalized_url": "https://www.youtube.com/@planeta_pubertat",
    },
    {
        "name": "channel_id_with_tracking",
        "url": "https://www.youtube.com/channel/UCALIGDpGpOmezPu0xujHzqA?si=abc123",
        "normalized_url": "https://www.youtube.com/channel/UCALIGDpGpOmezPu0xujHzqA",
    },
    {
        "name": "channel_custom_with_tracking",
        "url": "https://www.youtube.com/c/IDIM20247?feature=share",
        "normalized_url": "https://www.youtube.com/c/IDIM20247",
    },
    {
        "name": "channel_legacy_with_tracking",
        "url": "https://www.youtube.com/user/IDIM20247?feature=share",
        "normalized_url": "https://www.youtube.com/user/IDIM20247",
    },
    {
        "name": "playlist_with_tracking",
        "url": "https://www.youtube.com/playlist?list=PL1234567890&feature=share&pp=ygU",
        "normalized_url": "https://www.youtube.com/playlist?list=PL1234567890",
    },
    {
        "name": "clip_with_tracking",
        "url": "https://www.youtube.com/clip/UgkxMds3Y9ZTO-MNrUql234Cu6pwyLb-MW45?si=abc123",
        "normalized_url": "https://www.youtube.com/clip/UgkxMds3Y9ZTO-MNrUql234Cu6pwyLb-MW45",
    },
    {
        "name": "live_with_tracking",
        "url": "https://m.youtube.com/watch?v=0FBiyFpV__g&feature=share",
        "normalized_url": "https://www.youtube.com/watch?v=0FBiyFpV__g",
    },
    {
        "name": "embed_with_tracking",
        "url": "https://www.youtube.com/embed/lJIrF4YjHfQ?si=abc123",
        "normalized_url": "https://www.youtube.com/embed/lJIrF4YjHfQ",
    },
)

YOUTUBE_URL_SERVICE_CLASSIFICATION_CASES: Final[tuple[dict[str, str], ...]] = (
    {
        "name": "shorts",
        "url": SHORTS_URL,
        "expected_type": "shorts",
        "description": "Shorts URL уже поддерживается обработчиком.",
    },
    {
        "name": "shorts_with_query",
        "url": SHORTS_URL_WITH_QUERY,
        "expected_type": "shorts",
        "description": "Shorts URL с tracking-query должен распознаваться как shorts.",
    },
    {
        "name": "channel_handle",
        "url": CHANNEL_PROFILE_URL,
        "expected_type": "channel",
        "description": "Handle-страница канала уже поддерживается.",
    },
    {
        "name": "channel_id",
        "url": "https://www.youtube.com/channel/UCALIGDpGpOmezPu0xujHzqA",
        "expected_type": "channel",
        "description": "Канонический channel/<id> URL должен распознаваться как channel.",
    },
    {
        "name": "channel_custom",
        "url": "https://www.youtube.com/c/IDIM20247",
        "expected_type": "channel",
        "description": "Legacy c/<name> URL должен распознаваться как channel.",
    },
    {
        "name": "channel_legacy",
        "url": "https://www.youtube.com/user/IDIM20247",
        "expected_type": "channel",
        "description": "Legacy user/<name> URL должен распознаваться как channel.",
    },
    {
        "name": "video_watch",
        "url": WATCH_VIDEO_URL,
        "expected_type": "video",
        "description": "Обычная watch-ссылка на видео.",
    },
    {
        "name": "video_youtu_be",
        "url": YOUTU_BE_VIDEO_URL,
        "expected_type": "video",
        "description": "Short URL youtu.be должен классифицироваться как video.",
    },
    {
        "name": "video_live",
        "url": LIVE_VIDEO_URL,
        "expected_type": "video",
        "description": "Live URL должен попадать в video-like ветку.",
    },
    {
        "name": "video_embed",
        "url": "https://www.youtube.com/embed/lJIrF4YjHfQ",
        "expected_type": "video",
        "description": "Embed URL должен попадать в video-like ветку.",
    },
    {
        "name": "playlist_root",
        "url": "https://www.youtube.com/playlist?list=PL1234567890",
        "expected_type": "playlist",
        "description": "Playlist URL с list=<id> должен распознаваться как playlist.",
    },
    {
        "name": "video_with_playlist_param",
        "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL1234567890",
        "expected_type": "video",
        "description": "Watch URL с list=<id> должен оставаться video.",
    },
    {
        "name": "clip_root",
        "url": CLIP_URL,
        "expected_type": "clip",
        "description": "Clip URL должен распознаваться как clip.",
    },
)
