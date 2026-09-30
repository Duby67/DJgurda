"""Source contract: a module per site describes its links; the chat flow is shared."""

from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import SplitResult


def unknown_kind(url: SplitResult) -> str | None:
    return None


@dataclass(frozen=True)
class Source:
    name: str
    domains: tuple[str, ...]
    kind: Callable[[SplitResult], str | None] = unknown_kind
    downloadable: frozenset[str] = frozenset()

    def matches(self, host: str) -> bool:
        return any(host == domain or host.endswith("." + domain) for domain in self.domains)


@dataclass(frozen=True)
class Link:
    url: str
    source: Source
    kind: str | None

    @property
    def label(self) -> str:
        return f"{self.source.name}/{self.kind}" if self.kind else self.source.name

    @property
    def downloadable(self) -> bool:
        return self.kind in self.source.downloadable
