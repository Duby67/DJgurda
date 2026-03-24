#!/usr/bin/env python3
"""Helpers for planning and materializing isolated swarm workspaces."""

from __future__ import annotations

import json
import shutil
import subprocess

from dataclasses import dataclass
from pathlib import Path
from typing import Any


WORKTREE_MODE = "git_worktree"
SNAPSHOT_MODE = "snapshot_copy"
WORKSPACE_JSON_NAME = "workspace.json"
DEFAULT_CLEANUP_POLICY = "remove_after_run"
SNAPSHOT_EXCLUDED_DIRS = {".git", "runs", "venv", ".pytest_cache", "__pycache__"}
RUNTIME_DIRS_TO_PRUNE = SNAPSHOT_EXCLUDED_DIRS - {".git"}
VSCODE_SETTINGS_PATH = Path(".vscode/settings.json")


@dataclass(frozen=True)
class WorkspaceRef:
    """Machine-readable reference to an isolated workspace."""

    mode: str
    root_path: str
    base_ref: str
    source_head_sha: str
    source_branch: str
    source_remote: str
    source_dirty: bool
    cleanup_policy: str = DEFAULT_CLEANUP_POLICY

    def to_dict(self) -> dict[str, Any]:
        """Serializes the workspace reference."""
        return {
            "mode": self.mode,
            "root_path": self.root_path,
            "base_ref": self.base_ref,
            "source_head_sha": self.source_head_sha,
            "source_branch": self.source_branch,
            "source_remote": self.source_remote,
            "source_dirty": self.source_dirty,
            "cleanup_policy": self.cleanup_policy,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WorkspaceRef":
        """Deserializes the workspace reference."""
        return cls(
            mode=str(payload.get("mode", "")).strip(),
            root_path=str(payload.get("root_path", "")).strip(),
            base_ref=str(payload.get("base_ref", "")).strip(),
            source_head_sha=str(payload.get("source_head_sha", "")).strip(),
            source_branch=str(payload.get("source_branch", "")).strip(),
            source_remote=str(payload.get("source_remote", "")).strip(),
            source_dirty=bool(payload.get("source_dirty", False)),
            cleanup_policy=str(payload.get("cleanup_policy", DEFAULT_CLEANUP_POLICY)).strip() or DEFAULT_CLEANUP_POLICY,
        )


def normalize_rel_path(value: str) -> str:
    """Normalizes a path to a repo-friendly POSIX form."""
    return value.strip().replace("\\", "/").lstrip("./")


def _run_git(source_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Runs a git command inside a repository."""
    return subprocess.run(
        ["git", "-C", str(source_root), *args],
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def is_git_repository(source_root: Path) -> bool:
    """Checks whether the source root is a git repository."""
    result = _run_git(source_root, "rev-parse", "--is-inside-work-tree")
    return result.returncode == 0 and result.stdout.strip().casefold() == "true"


def is_git_dirty(source_root: Path) -> bool:
    """Checks whether the repository has local modifications."""
    result = _run_git(source_root, "status", "--porcelain=v1", "--untracked-files=all")
    if result.returncode != 0:
        raise RuntimeError(f"git status failed: {result.stderr.strip() or result.stdout.strip()}")
    return bool(result.stdout.strip())


def get_git_head_ref(source_root: Path) -> str:
    """Returns a compact base ref for the current source tree."""
    result = _run_git(source_root, "rev-parse", "--short", "HEAD")
    if result.returncode == 0:
        ref = result.stdout.strip()
        if ref:
            return ref
    return "HEAD"


def get_git_head_sha(source_root: Path) -> str:
    """Returns the full HEAD SHA when available."""
    result = _run_git(source_root, "rev-parse", "HEAD")
    if result.returncode == 0:
        ref = result.stdout.strip()
        if ref:
            return ref
    return ""


def get_git_head_branch(source_root: Path) -> str:
    """Returns the current source branch when HEAD is attached."""
    result = _run_git(source_root, "rev-parse", "--abbrev-ref", "HEAD")
    if result.returncode == 0:
        branch = result.stdout.strip()
        if branch and branch != "HEAD":
            return branch
    return ""


def get_git_default_remote(source_root: Path) -> str:
    """Returns the preferred remote name for the source repository."""
    origin = _run_git(source_root, "config", "--get", "remote.origin.url")
    if origin.returncode == 0 and origin.stdout.strip():
        return "origin"

    remotes = _run_git(source_root, "remote")
    if remotes.returncode == 0:
        for line in remotes.stdout.splitlines():
            remote = line.strip()
            if remote:
                return remote
    return ""


def _is_snapshot_path_allowed(rel_path: str) -> bool:
    """Filters out runtime/workspace paths from snapshot materialization."""
    normalized = normalize_rel_path(rel_path)
    if not normalized:
        return False
    parts = Path(normalized).parts
    if any(part in SNAPSHOT_EXCLUDED_DIRS for part in parts):
        return False
    return True


def collect_snapshot_paths(source_root: Path) -> list[str]:
    """Collects tracked and untracked non-ignored files for snapshot mode."""
    result = _run_git(
        source_root,
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        "-z",
    )
    if result.returncode != 0:
        raise RuntimeError(f"git ls-files failed: {result.stderr.strip() or result.stdout.strip()}")

    paths: list[str] = []
    seen: set[str] = set()
    for raw_item in result.stdout.split("\0"):
        if not raw_item:
            continue
        rel_path = normalize_rel_path(raw_item)
        if not _is_snapshot_path_allowed(rel_path):
            continue
        absolute = source_root / rel_path
        if not absolute.is_file():
            continue
        if rel_path in seen:
            continue
        seen.add(rel_path)
        paths.append(rel_path)
    return paths


def build_workspace_ref(
    *,
    source_root: Path,
    workspace_root: Path,
    cleanup_policy: str = DEFAULT_CLEANUP_POLICY,
) -> WorkspaceRef:
    """Builds a workspace reference and selects the isolation mode."""
    if not is_git_repository(source_root):
        raise ValueError(f"Source root is not a git repository: {source_root}")

    source_dirty = is_git_dirty(source_root)
    mode = SNAPSHOT_MODE if source_dirty else WORKTREE_MODE
    return WorkspaceRef(
        mode=mode,
        root_path=str(workspace_root),
        base_ref=get_git_head_ref(source_root),
        source_head_sha=get_git_head_sha(source_root),
        source_branch=get_git_head_branch(source_root),
        source_remote=get_git_default_remote(source_root),
        source_dirty=source_dirty,
        cleanup_policy=cleanup_policy,
    )


def _ensure_empty_workspace_root(workspace_root: Path) -> None:
    if workspace_root.exists() and any(workspace_root.iterdir()):
        raise FileExistsError(f"Workspace root is not empty: {workspace_root}")
    workspace_root.parent.mkdir(parents=True, exist_ok=True)


def materialize_git_worktree(
    *,
    source_root: Path,
    workspace_root: Path,
    base_ref: str,
) -> dict[str, Any]:
    """Creates a detached git worktree at the target location."""
    _ensure_empty_workspace_root(workspace_root)
    result = _run_git(source_root, "worktree", "add", "--force", "--detach", str(workspace_root), base_ref)
    if result.returncode != 0:
        raise RuntimeError(f"git worktree add failed: {result.stderr.strip() or result.stdout.strip()}")
    return {
        "mode": WORKTREE_MODE,
        "workspace_root": str(workspace_root),
        "created": True,
        "git_worktree_command": [
            "git",
            "-C",
            str(source_root),
            "worktree",
            "add",
            "--force",
            "--detach",
            str(workspace_root),
            base_ref,
        ],
    }


def overlay_snapshot(
    *,
    source_root: Path,
    workspace_root: Path,
    snapshot_paths: list[str],
) -> dict[str, Any]:
    """Overlays dirty tracked/untracked files on top of a clean worktree."""
    copied_paths: list[str] = []

    for rel_path in snapshot_paths:
        source_path = source_root / rel_path
        if not source_path.is_file():
            continue
        destination_path = workspace_root / rel_path
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination_path)
        copied_paths.append(rel_path)

    return {
        "mode": SNAPSHOT_MODE,
        "workspace_root": str(workspace_root),
        "copied_paths": copied_paths,
        "file_count": len(copied_paths),
    }


def prune_runtime_dirs(workspace_root: Path) -> dict[str, Any]:
    """Removes runtime-only directories from a dirty workspace overlay."""
    removed_paths: list[str] = []
    for dirname in sorted(RUNTIME_DIRS_TO_PRUNE):
        candidate = workspace_root / dirname
        if not candidate.exists():
            continue
        if candidate.is_dir():
            shutil.rmtree(candidate, ignore_errors=True)
            removed_paths.append(dirname)
    return {
        "workspace_root": str(workspace_root),
        "removed_paths": removed_paths,
        "removed_count": len(removed_paths),
    }


def sync_workspace_vscode_settings(source_root: Path, workspace_root: Path) -> dict[str, Any]:
    """Points isolated VSCode workspace settings at the source-root venv."""
    source_settings_path = source_root / VSCODE_SETTINGS_PATH
    workspace_settings_path = workspace_root / VSCODE_SETTINGS_PATH
    interpreter_path = source_root / "venv" / "Scripts" / "python.exe"
    activate_path = source_root / "venv" / "Scripts" / "activate.bat"

    if not source_settings_path.is_file() or not workspace_settings_path.is_file():
        return {
            "updated": False,
            "reason": "settings_file_missing",
        }

    if not interpreter_path.is_file() or not activate_path.is_file():
        return {
            "updated": False,
            "reason": "source_venv_missing",
        }

    try:
        settings = json.loads(workspace_settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "updated": False,
            "reason": "settings_json_invalid",
        }

    if not isinstance(settings, dict):
        return {
            "updated": False,
            "reason": "settings_payload_invalid",
        }

    settings["python.defaultInterpreterPath"] = str(interpreter_path)
    settings["terminal.integrated.defaultProfile.windows"] = "Command Prompt (venv)"
    profiles = settings.setdefault("terminal.integrated.profiles.windows", {})
    if not isinstance(profiles, dict):
        profiles = {}
        settings["terminal.integrated.profiles.windows"] = profiles
    profiles["Command Prompt (venv)"] = {
        "path": "${env:ComSpec}",
        "args": [
            "/k",
            str(activate_path),
        ],
    }

    workspace_settings_path.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "updated": True,
        "settings_path": str(workspace_settings_path),
        "interpreter_path": str(interpreter_path),
        "activate_path": str(activate_path),
    }


def build_workspace_plan(
    *,
    source_root: Path,
    workspace_root: Path,
    cleanup_policy: str = DEFAULT_CLEANUP_POLICY,
) -> dict[str, Any]:
    """Builds a machine-readable workspace plan."""
    workspace = build_workspace_ref(
        source_root=source_root,
        workspace_root=workspace_root,
        cleanup_policy=cleanup_policy,
    )
    materialization: dict[str, Any] = {
        "mode": workspace.mode,
        "git_worktree_command": [
            "git",
            "-C",
            str(source_root),
            "worktree",
            "add",
            "--force",
            "--detach",
            str(workspace_root),
            workspace.base_ref,
        ],
    }
    if workspace.mode == WORKTREE_MODE:
        materialization["snapshot_paths"] = []
    else:
        materialization["snapshot_paths"] = collect_snapshot_paths(source_root)

    return {
        "version": 1,
        "source_root": str(source_root),
        "workspace_root": str(workspace_root),
        "workspace": workspace.to_dict(),
        "materialization": materialization,
    }


def prepare_workspace(
    *,
    source_root: Path,
    workspace_root: Path,
    cleanup_policy: str = DEFAULT_CLEANUP_POLICY,
) -> dict[str, Any]:
    """Builds a workspace plan and materializes the isolated workspace."""
    plan = build_workspace_plan(
        source_root=source_root,
        workspace_root=workspace_root,
        cleanup_policy=cleanup_policy,
    )

    git_worktree = materialize_git_worktree(
        source_root=source_root,
        workspace_root=workspace_root,
        base_ref=plan["workspace"]["base_ref"],
    )
    if plan["workspace"]["mode"] == SNAPSHOT_MODE:
        snapshot_overlay = overlay_snapshot(
            source_root=source_root,
            workspace_root=workspace_root,
            snapshot_paths=plan["materialization"]["snapshot_paths"],
        )
        runtime_prune = prune_runtime_dirs(workspace_root)
        plan["materialized"] = {
            "mode": SNAPSHOT_MODE,
            "git_worktree": git_worktree,
            "snapshot_overlay": snapshot_overlay,
            "runtime_prune": runtime_prune,
        }
    else:
        plan["materialized"] = git_worktree
    plan["editor_support"] = sync_workspace_vscode_settings(source_root, workspace_root)
    return plan


def resolve_workspace_json_path(path: Path) -> Path:
    """Resolves either a run directory or an explicit workspace.json path."""
    if path.suffix.lower() == ".json":
        return path
    return path / WORKSPACE_JSON_NAME


def write_workspace_json(
    path: Path,
    *,
    workspace: WorkspaceRef,
    plan: dict[str, Any] | None = None,
) -> Path:
    """Writes workspace metadata to workspace.json."""
    workspace_json_path = resolve_workspace_json_path(path)
    workspace_json_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "workspace": workspace.to_dict(),
    }
    if plan is not None:
        payload["plan"] = plan

    workspace_json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return workspace_json_path


def read_workspace_json(path: Path) -> dict[str, Any]:
    """Reads workspace metadata from workspace.json."""
    workspace_json_path = resolve_workspace_json_path(path)
    return json.loads(workspace_json_path.read_text(encoding="utf-8"))


def read_workspace_ref(path: Path) -> WorkspaceRef:
    """Reads workspace metadata and returns the workspace reference."""
    payload = read_workspace_json(path)
    if "workspace" not in payload or not isinstance(payload["workspace"], dict):
        raise ValueError("workspace.json is missing a valid 'workspace' object")
    return WorkspaceRef.from_dict(payload["workspace"])


def resolve_workspace_root(path: Path, *, fallback: Path | None = None) -> Path:
    """Resolves a workspace root from workspace.json, falling back if absent."""
    workspace_json_path = resolve_workspace_json_path(path)
    if not workspace_json_path.is_file():
        if fallback is None:
            raise FileNotFoundError(f"Workspace metadata not found: {workspace_json_path}")
        return fallback
    return Path(read_workspace_ref(workspace_json_path).root_path)


def cleanup_workspace(
    path: Path,
    *,
    source_root: Path,
    keep_workspace: bool = False,
) -> dict[str, Any]:
    """Removes the isolated workspace unless it is explicitly preserved."""
    workspace_json_path = resolve_workspace_json_path(path)
    if keep_workspace:
        return {
            "skipped": True,
            "reason": "keep_workspace_requested",
        }
    if not workspace_json_path.is_file():
        return {
            "skipped": True,
            "reason": "workspace_metadata_missing",
        }

    workspace_root = Path(read_workspace_ref(workspace_json_path).root_path)
    if not workspace_root.exists():
        return {
            "skipped": True,
            "reason": "workspace_root_missing",
            "workspace_root": str(workspace_root),
        }

    result = _run_git(source_root, "worktree", "remove", "--force", str(workspace_root))
    if result.returncode != 0:
        shutil.rmtree(workspace_root, ignore_errors=True)
        return {
            "skipped": False,
            "mode": "fallback_rmtree",
            "workspace_root": str(workspace_root),
        }

    return {
        "skipped": False,
        "mode": "git_worktree_remove",
        "workspace_root": str(workspace_root),
    }
