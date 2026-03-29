"""Configuration for cookies extractor scripts."""

from __future__ import annotations

from dataclasses import dataclass
from os import getenv
from pathlib import Path


def _to_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class ExtractorConfig:
    browser: str = "firefox"
    browser_profile: str | None = "/cookies_extractor/firefox_profile"
    output_dir: Path = Path("/cookies_extractor/cookies")
    targets: str = "youtube,vk,instagram,tiktok,coub"
    min_cookies: int = 1


def load_config() -> ExtractorConfig:
    browser = getenv("COOKIES_BROWSER", "firefox")
    browser_profile = getenv("COOKIES_BROWSER_PROFILE", "/cookies_extractor/firefox_profile") or None
    output_dir = Path(getenv("COOKIES_OUTPUT_DIR", "/cookies_extractor/cookies"))
    targets = getenv("COOKIES_TARGETS", "youtube,vk,instagram,tiktok,coub")
    min_cookies = _to_int(getenv("COOKIES_MIN_COOKIES"), 1)

    return ExtractorConfig(
        browser=browser,
        browser_profile=browser_profile,
        output_dir=output_dir,
        targets=targets,
        min_cookies=min_cookies,
    )
