from __future__ import annotations

import json
import subprocess
import sys

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def run_module(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def test_route_module_smoke_for_release_docs() -> None:
    result = run_module(
        "-m",
        "scripts.agents.routing.route",
        "--prompt",
        "Обновить release flow документацию",
        "--path",
        "docs/release-flow.md",
        "--pretty",
    )

    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert payload["task_type"]["id"] == "release_or_versioning_change"
    assert "scripts/AGENTS.md" in payload["context_pack"]["agents"]
    assert "scripts/release/automation/promote.py" in payload["context_pack"]["code"]


def test_release_promote_preview_dry_run_smoke() -> None:
    result = run_module(
        "-m",
        "scripts.release.automation.promote",
        "--source-branch",
        "swarm-dev",
        "--target-branch",
        "dev",
        "--target-kind",
        "preview",
        "--pretty",
    )

    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert payload["mode"] == "dry_run"
    assert payload["plan"]["target_branch"] == "dev"
    assert payload["plan"]["target_kind"] == "preview"
    assert payload["plan"]["next_release"]["tag"].startswith("v")


def test_release_sync_smoke_for_current_prod_tag() -> None:
    result = run_module(
        "-m",
        "scripts.release.automation.sync",
        "--tag",
        "v1.2.4",
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "OK: src.__version__ == tag" in result.stdout
