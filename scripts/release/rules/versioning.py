#!/usr/bin/env python3
"""Общие правила версионирования для stable и preview release-потоков."""

from __future__ import annotations

import re

from dataclasses import dataclass


VERSION_RE = re.compile(r"^(?:refs/tags/)?v?(\d+)\.(\d+)\.(\d+)(?:_([a-z]+))?$")


def alpha_suffix_to_number(value: str) -> int:
    """Преобразует alpha suffix в число по схеме a=1, z=26, aa=27."""
    if not value or not value.isalpha() or not value.islower():
        raise ValueError(f"Неподдерживаемый preview suffix: '{value}'")

    result = 0
    for char in value:
        result = result * 26 + (ord(char) - ord("a") + 1)
    return result


def number_to_alpha_suffix(value: int) -> str:
    """Преобразует положительное число в alpha suffix по схеме a=1, z=26, aa=27."""
    if value <= 0:
        raise ValueError("Preview suffix number должен быть положительным")

    chars: list[str] = []
    current = value
    while current > 0:
        current -= 1
        chars.append(chr(ord("a") + (current % 26)))
        current //= 26
    return "".join(reversed(chars))


def increment_alpha_suffix(value: str) -> str:
    """Инкрементирует preview suffix: a -> b, z -> aa."""
    return number_to_alpha_suffix(alpha_suffix_to_number(value) + 1)


@dataclass(frozen=True)
class ReleaseVersion:
    major: int
    minor: int
    patch: int
    preview_suffix: str | None = None

    def normalized(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        if self.preview_suffix:
            return f"{base}_{self.preview_suffix}"
        return base

    def tag(self, prefix: str = "v") -> str:
        return f"{prefix}{self.normalized()}"

    @property
    def is_preview(self) -> bool:
        return self.preview_suffix is not None

    def stable(self) -> "ReleaseVersion":
        return ReleaseVersion(self.major, self.minor, self.patch)

    def next_stable(self) -> "ReleaseVersion":
        if self.patch < 9:
            return ReleaseVersion(self.major, self.minor, self.patch + 1)
        return ReleaseVersion(self.major, self.minor + 1, 0)

    def start_preview_cycle(self) -> "ReleaseVersion":
        return ReleaseVersion(self.major, self.minor, self.patch, "a")

    def next_preview(self) -> "ReleaseVersion":
        if not self.preview_suffix:
            return self.start_preview_cycle()
        return ReleaseVersion(
            self.major,
            self.minor,
            self.patch,
            increment_alpha_suffix(self.preview_suffix),
        )

    def sort_key(self) -> tuple[int, int, int, int, int]:
        preview_rank = alpha_suffix_to_number(self.preview_suffix) if self.preview_suffix else 0
        stable_marker = 0 if self.preview_suffix else 1
        return (self.major, self.minor, self.patch, stable_marker, preview_rank)


def parse_release_version(value: str) -> ReleaseVersion:
    """Парсит строку версии вида 1.2.3, v1.2.3, 1.2.3_a или v1.2.3_a."""
    normalized = value.strip()
    match = VERSION_RE.fullmatch(normalized)
    if not match:
        raise ValueError(f"Неподдерживаемая release-версия: '{value}'")
    return ReleaseVersion(
        major=int(match.group(1)),
        minor=int(match.group(2)),
        patch=int(match.group(3)),
        preview_suffix=match.group(4),
    )


def normalize_tag(value: str, prefix: str = "v") -> str:
    """Нормализует tag до строки версии без refs/tags/ и префикса."""
    normalized = value.strip()
    if normalized.startswith("refs/tags/"):
        normalized = normalized[len("refs/tags/") :]
    if prefix and normalized.startswith(prefix):
        normalized = normalized[len(prefix) :]
    return normalized


def is_release_version(value: str) -> bool:
    """Проверяет, можно ли распарсить строку как release-версию."""
    try:
        parse_release_version(value)
    except ValueError:
        return False
    return True
