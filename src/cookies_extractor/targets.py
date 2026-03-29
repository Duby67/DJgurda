"""Known cookie extraction targets and helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CookieTarget:
    key: str
    folder: str
    output_file: str
    domains: tuple[str, ...]
    min_cookies: int = 1


KNOWN_TARGETS: dict[str, CookieTarget] = {
    "youtube": CookieTarget(
        key="youtube",
        folder="YouTube",
        output_file="www.youtube.com_cookies.txt",
        domains=("youtube.com", "google.com", "youtu.be", "googlevideo.com"),
        min_cookies=1,
    ),
    "vk": CookieTarget(
        key="vk",
        folder="VK",
        output_file="vk.com_cookies.txt",
        domains=("vk.com",),
        min_cookies=1,
    ),
    "instagram": CookieTarget(
        key="instagram",
        folder="Instagram",
        output_file="www.instagram.com_cookies.txt",
        domains=("instagram.com",),
        min_cookies=1,
    ),
    "tiktok": CookieTarget(
        key="tiktok",
        folder="TikTok",
        output_file="www.tiktok.com_cookies.txt",
        domains=("tiktok.com",),
        min_cookies=1,
    ),
    "coub": CookieTarget(
        key="coub",
        folder="Coub",
        output_file="coub.com_cookies.txt",
        domains=("coub.com",),
        min_cookies=1,
    ),
}

ALIASES: dict[str, str] = {
    "yt": "youtube",
    "youtube": "youtube",
    "vk": "vk",
    "vkontakte": "vk",
    "instagram": "instagram",
    "insta": "instagram",
    "tiktok": "tiktok",
    "tt": "tiktok",
    "coub": "coub",
}


def parse_targets(raw: str) -> list[CookieTarget]:
    keys = [token.strip().lower() for token in raw.split(",") if token.strip()]
    if not keys:
        keys = ["youtube", "vk", "instagram", "tiktok", "coub"]

    resolved: list[CookieTarget] = []
    seen: set[str] = set()

    for key in keys:
        canonical = ALIASES.get(key)
        if canonical is None:
            available = ", ".join(sorted(KNOWN_TARGETS))
            raise ValueError(f"Unknown target '{key}'. Available targets: {available}")

        if canonical in seen:
            continue

        resolved.append(KNOWN_TARGETS[canonical])
        seen.add(canonical)

    return resolved
