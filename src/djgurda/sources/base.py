"""Source contract: a module per site describes its links and how to fetch them.

The chat flow (reading messages, captions, delivery) is shared by all sources.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import SplitResult

from djgurda.media import Job, Media, download


def unknown(url: SplitResult) -> None:
    return None


def within(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


@dataclass(frozen=True)
class Source:
    name: str
    domains: tuple[str, ...]
    kind: Callable[[SplitResult], str | None] = unknown
    downloadable: frozenset[str] = frozenset()
    media_id: Callable[[SplitResult], str | None] = unknown  # Stable id for the file_id cache.
    start: Callable[[SplitResult], int | None] = unknown  # Playback start in seconds.
    # Mirror domain -> real domain, e.g. kkinstagram.com -> instagram.com; subdomains are kept.
    aliases: tuple[tuple[str, str], ...] = ()
    tracking: frozenset[str] = frozenset()  # Query parameters dropped from the canonical link.
    audio: frozenset[str] = frozenset()  # Kinds delivered as audio instead of video.
    fetch: Callable[[str, Path, Job], Media] = download  # Canonical URL -> downloaded media.

    def canonical_host(self, host: str) -> str | None:
        if any(within(host, domain) for domain in self.domains):
            return host
        for alias, domain in self.aliases:
            if within(host, alias):
                return host.removesuffix(alias) + domain
        return None


@dataclass(frozen=True)
class Link:
    url: str  # Canonical: real domain, no tracking parameters.
    source: Source
    kind: str | None
    media_id: str | None = None
    start: int | None = None

    @property
    def label(self) -> str:
        return f"{self.source.name}/{self.kind}" if self.kind else self.source.name

    @property
    def key(self) -> str | None:
        return f"{self.source.name}:{self.kind}:{self.media_id}" if self.media_id else None

    @property
    def downloadable(self) -> bool:
        return self.kind in self.source.downloadable

    @property
    def audio(self) -> bool:
        return self.kind in self.source.audio
