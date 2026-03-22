#!/usr/bin/env python3
"""Shared policy/knowledge helpers for swarm planning and verification."""

from __future__ import annotations

import json
import re

from pathlib import Path
from typing import Any

from scripts.config import ROOT


VERIFICATION_PROFILES_PATH = ROOT / "docs" / "verification-profiles.json"
PLANS_INDEX_PATH = ROOT / "docs" / "PLANS.md"
ACTIVE_PLANS_INDEX_PATH = ROOT / "docs" / "exec-plans" / "active" / "index.md"
TECH_DEBT_TRACKER_PATH = ROOT / "docs" / "exec-plans" / "tech-debt-tracker.md"
REFACTORING_PATH = ROOT / "local" / "REFACTORING.md"


def load_json(path: Path) -> dict[str, Any]:
    """Loads a JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_rel_path(value: str) -> str:
    """Normalizes a repository-relative path."""
    return value.strip().replace("\\", "/").lstrip("./")


def load_verification_profiles() -> dict[str, Any]:
    """Loads verification profile definitions."""
    return load_json(VERIFICATION_PROFILES_PATH)


def get_verification_profile(task_type_id: str) -> dict[str, Any]:
    """Returns verification profile for a task type."""
    payload = load_verification_profiles()
    profiles = payload.get("profiles", {})
    if task_type_id not in profiles:
        raise KeyError(f"Verification profile not found for task type '{task_type_id}'")
    return profiles[task_type_id]


def path_matches_area(path: str, area: str) -> bool:
    """Checks whether a changed path matches an area marker."""
    normalized_path = normalize_rel_path(path)
    normalized_area = normalize_rel_path(area)

    if normalized_area in {"tracked docs", "tracked-docs", "docs"}:
        return (
            normalized_path.startswith("docs/")
            or normalized_path in {"AGENTS.md", "ARCHITECTURE.md", "README.md"}
        )
    if normalized_area in {"tracked code comments and docstrings", "tracked code comments", "docstrings"}:
        return normalized_path.startswith("src/")
    if normalized_area.startswith(".github/"):
        return normalized_path == normalized_area
    return normalized_path == normalized_area or normalized_path.startswith(normalized_area.rstrip("/") + "/")


def parse_markdown_risks(path: Path, *, source: str) -> list[dict[str, Any]]:
    """Parses markdown risk/debt entries with area markers."""
    if not path.is_file():
        return []

    lines = path.read_text(encoding="utf-8").splitlines()
    entries: list[dict[str, Any]] = []
    current_priority = "unknown"
    current: dict[str, Any] | None = None
    collecting_areas = False
    collecting_impact = False

    def strip_inline_marker(value: str, markers: tuple[str, ...]) -> str:
        for marker in markers:
            if value.startswith(marker):
                return value[len(marker):].strip().strip("`")
        return ""

    def flush_current() -> None:
        nonlocal current
        if current is not None:
            current["areas"] = list(dict.fromkeys(current.get("areas", [])))
            current["impact"] = " ".join(current.get("impact_lines", [])).strip()
            current.pop("impact_lines", None)
            entries.append(current)
            current = None

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()

        if stripped.startswith("## "):
            lower = stripped.casefold()
            if "high priority" in lower:
                current_priority = "high"
            elif "medium priority" in lower:
                current_priority = "medium"
            elif "low priority" in lower:
                current_priority = "low"

        if stripped.startswith("### ") or stripped.startswith("#### "):
            flush_current()
            title = re.sub(r"^[#\s0-9).]+", "", stripped).strip()
            current = {
                "title": title,
                "priority": current_priority,
                "source": source,
                "areas": [],
                "impact_lines": [],
            }
            collecting_areas = False
            collecting_impact = False
            continue

        if current is None:
            continue

        lower = stripped.casefold()
        if stripped.startswith("- Main Area:") or stripped.startswith("- Main Areas:") or stripped.startswith("- Где:"):
            collecting_areas = True
            collecting_impact = False
            inline_area = strip_inline_marker(
                stripped,
                ("- Main Area:", "- Main Areas:", "- Где:"),
            )
            if inline_area:
                current["areas"].append(inline_area)
            continue
        if stripped.startswith("- Impact:") or stripped.startswith("- Почему важно:"):
            collecting_impact = True
            collecting_areas = False
            inline_impact = strip_inline_marker(
                stripped,
                ("- Impact:", "- Почему важно:"),
            )
            if inline_impact:
                current["impact_lines"].append(inline_impact)
            continue
        if stripped.startswith("- ") and not stripped.startswith("- Problem:") and not stripped.startswith("- Что делать:"):
            if collecting_areas:
                current["areas"].append(stripped[2:].strip().strip("`"))
                continue
            if collecting_impact:
                current["impact_lines"].append(stripped[2:].strip())
                continue

        if collecting_areas and stripped and not stripped.startswith("- "):
            collecting_areas = False
        if collecting_impact and stripped and not stripped.startswith("- "):
            collecting_impact = False

    flush_current()
    return entries


def collect_known_risks(changed_paths: list[str], task_type_id: str) -> dict[str, Any]:
    """Collects relevant risks from tracked and archive backlog sources."""
    risks: list[dict[str, Any]] = []
    changed_paths = [normalize_rel_path(item) for item in changed_paths]

    for source_path, source_name, allow_archive in (
        (TECH_DEBT_TRACKER_PATH, "tech_debt_tracker", False),
        (REFACTORING_PATH, "refactoring_archive", True),
    ):
        for entry in parse_markdown_risks(source_path, source=source_name):
            matched_areas = [area for area in entry.get("areas", []) if any(path_matches_area(path, area) for path in changed_paths)]
            if not matched_areas:
                continue
            if source_name == "refactoring_archive" and task_type_id == "docs_only_change":
                continue
            risks.append(
                {
                    "title": entry["title"],
                    "priority": entry["priority"],
                    "source": source_name,
                    "matched_areas": matched_areas,
                    "impact": entry.get("impact", ""),
                    "archive_input": allow_archive,
                }
            )

    seen: set[tuple[str, str]] = set()
    unique_risks: list[dict[str, Any]] = []
    for risk in risks:
        key = (risk["source"], risk["title"])
        if key in seen:
            continue
        seen.add(key)
        unique_risks.append(risk)

    return {
        "risk_sources": [
            str(TECH_DEBT_TRACKER_PATH.relative_to(ROOT)).replace("\\", "/"),
            str(REFACTORING_PATH.relative_to(ROOT)).replace("\\", "/"),
        ],
        "known_risks": unique_risks,
    }


def collect_active_initiatives(changed_paths: list[str], task_type_id: str) -> dict[str, Any]:
    """Collects active initiatives relevant to current paths."""
    initiatives: list[dict[str, Any]] = []
    changed_paths = [normalize_rel_path(item) for item in changed_paths]

    if ACTIVE_PLANS_INDEX_PATH.is_file():
        for line in ACTIVE_PLANS_INDEX_PATH.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped.startswith("- `docs/exec-plans/active/"):
                continue
            rel_path = stripped.split("`", 2)[1]
            relevant = (
                any(path.startswith("docs/") or path.startswith("scripts/agents/") for path in changed_paths)
                or task_type_id in {"docs_only_change", "release_or_versioning_change"}
            )
            if relevant:
                initiatives.append(
                    {
                        "path": rel_path,
                        "relevance": "docs_or_swarm_change",
                    }
                )

    return {
        "active_initiative_sources": [
            str(PLANS_INDEX_PATH.relative_to(ROOT)).replace("\\", "/"),
            str(ACTIVE_PLANS_INDEX_PATH.relative_to(ROOT)).replace("\\", "/"),
        ],
        "active_initiatives": initiatives,
    }
