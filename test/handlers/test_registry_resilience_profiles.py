"""Tests for explicit resilience posture in the runtime handler registry."""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("BOT_DB_PATH", str(PROJECT_ROOT / "src" / "data" / "db" / "bot.db"))
os.environ.setdefault("BOT_VERSION", "local-test")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("BOT_TOKEN", "local-test-token")
os.environ.setdefault("YANDEX_MUSIC_TOKEN", "local-test-token")
os.environ.setdefault("YOUTUBE_COOKIES_ENABLED", "false")

from src.handlers.registry import get_default_handler_registry, get_non_runtime_source_statuses


def test_stable_runtime_descriptors_define_explicit_resilience_profiles() -> None:
    """Every stable runtime source should carry a non-empty resilience profile."""
    registry = get_default_handler_registry()

    descriptors_by_source = {
        descriptor.source_name: descriptor
        for descriptor in registry.descriptors
    }

    assert set(descriptors_by_source) == {
        "TikTok",
        "YouTube",
        "Instagram",
        "COUB",
        "Yandex.Music",
    }

    for descriptor in descriptors_by_source.values():
        profile = descriptor.resilience_profile
        assert profile.dependency_surfaces
        assert profile.timeout_expectations
        assert profile.retry_expectations
        assert profile.degrade_signals
        assert profile.degrade_behavior


def test_vk_remains_non_runtime_source_with_separate_status() -> None:
    """VK should stay outside the stable runtime resilience contract."""
    registry = get_default_handler_registry()
    source_names = {descriptor.source_name for descriptor in registry.descriptors}

    assert "VK" not in source_names
    assert get_non_runtime_source_statuses() == {"VK": "in_development"}


def test_resilience_profiles_capture_source_specific_signals() -> None:
    """Known high-risk sources should expose their key degrade signals explicitly."""
    registry = get_default_handler_registry()
    descriptors_by_source = {
        descriptor.source_name: descriptor
        for descriptor in registry.descriptors
    }

    assert "tiktok_fallback_to_ytdlp" in descriptors_by_source["TikTok"].resilience_profile.degrade_signals
    assert "youtube_format_fallback" in descriptors_by_source["YouTube"].resilience_profile.degrade_signals
    assert "instagram_web_profile_info_failed" in descriptors_by_source["Instagram"].resilience_profile.degrade_signals
    assert "coub_pipeline_exhausted" in descriptors_by_source["COUB"].resilience_profile.degrade_signals
    assert "yandex_music_token_missing" in descriptors_by_source["Yandex.Music"].resilience_profile.degrade_signals
