"""Configuration for YouTube cookies extractor scripts."""

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
    domain: str = "youtube.com"
    output_dir: Path = Path("/cookies_extractor/cookies")
    output_file: str = "www.youtube.com_cookies.txt"
    min_cookies: int = 1

    @property
    def output_path(self) -> Path:
        return self.output_dir / self.output_file


def load_config() -> ExtractorConfig:
    browser = getenv("COOKIES_BROWSER", "firefox")
    browser_profile = getenv("COOKIES_BROWSER_PROFILE", "/cookies_extractor/firefox_profile") or None
    domain = getenv("COOKIES_DOMAIN", "youtube.com")
    output_dir = Path(getenv("COOKIES_OUTPUT_DIR", "/cookies_extractor/cookies"))
    output_file = getenv("COOKIES_OUTPUT_FILE", "www.youtube.com_cookies.txt")
    min_cookies = _to_int(getenv("COOKIES_MIN_COOKIES"), 1)

    return ExtractorConfig(
        browser=browser,
        browser_profile=browser_profile,
        domain=domain,
        output_dir=output_dir,
        output_file=output_file,
        min_cookies=min_cookies,
    )


