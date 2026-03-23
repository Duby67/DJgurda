#!/usr/bin/env python3
"""Helpers for append-only swarm runtime context tracing."""

from __future__ import annotations

import json

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.config import ROOT


RUNTIME_CONTEXT_TRACE_NAME = "runtime-context-trace.jsonl"
VALID_RESOLUTIONS = {"resolved", "abstract", "missing", "advisory", "blocking"}


def now_utc() -> str:
    """Returns an ISO8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def runtime_trace_path(run_dir: Path) -> Path:
    """Returns the runtime trace artifact path."""
    return run_dir / RUNTIME_CONTEXT_TRACE_NAME


def artifact_rel_path(path: Path) -> str:
    """Converts an absolute path under ROOT into a repo-relative POSIX path."""
    return str(path.relative_to(ROOT)).replace("\\", "/")


def load_runtime_trace(run_dir: Path) -> list[dict[str, Any]]:
    """Loads runtime trace events from disk."""
    path = runtime_trace_path(run_dir)
    if not path.is_file():
        return []

    events: list[dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        events.append(json.loads(stripped))
    return events


def append_runtime_trace_event(
    run_dir: Path,
    *,
    phase: str,
    job_id: str,
    requested_by: str,
    category: str,
    item: str,
    reason: str,
    source_artifact: str,
    resolution: str,
    before_summary: dict[str, Any] | None = None,
    after_summary: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Appends one runtime trace event to the run bundle."""
    if resolution not in VALID_RESOLUTIONS:
        raise ValueError(f"Unsupported runtime trace resolution: {resolution}")

    event = {
        "timestamp_utc": now_utc(),
        "phase": phase,
        "job_id": job_id,
        "requested_by": requested_by,
        "category": category,
        "item": item,
        "reason": reason,
        "source_artifact": source_artifact,
        "resolution": resolution,
    }
    if before_summary is not None:
        event["before_summary"] = before_summary
    if after_summary is not None:
        event["after_summary"] = after_summary
    if extra:
        event["extra"] = extra

    path = runtime_trace_path(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def summarize_runtime_trace(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Builds a compact summary for runtime trace events."""
    by_phase: dict[str, int] = {}
    by_resolution: dict[str, int] = {}

    for event in events:
        phase = str(event.get("phase", "unknown"))
        resolution = str(event.get("resolution", "unknown"))
        by_phase[phase] = by_phase.get(phase, 0) + 1
        by_resolution[resolution] = by_resolution.get(resolution, 0) + 1

    return {
        "total_events": len(events),
        "by_phase": by_phase,
        "by_resolution": by_resolution,
        "latest_event": events[-1] if events else None,
    }
