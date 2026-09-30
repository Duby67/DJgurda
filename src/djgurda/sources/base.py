"""Source contract: a module per site describes its links; the chat flow is shared."""

from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import SplitResult


def unknown(url: SplitResult) -> None:
    return None


@dataclass(frozen=True)
class Source:
    name: str
    domains: tuple[str, ...]
    kind: Callable[[SplitResult], str | None] = unknown
    downloadable: frozenset[str] = frozenset()
    media_id: Callable[[SplitResult], str | None] = unknown  # Stable id for the file_id cache.
    start: Callable[[SplitResult], int | None] = unknown  # Playback start in seconds.

    def matches(self, host: str) -> bool:
        return any(host == domain or host.endswith("." + domain) for domain in self.domains)


@dataclass(frozen=True)
class Link:
    url: str
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
