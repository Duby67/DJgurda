from __future__ import annotations

import json
import subprocess

from pathlib import Path

from scripts.agents.workspace import (
    SNAPSHOT_MODE,
    WORKTREE_MODE,
    WorkspaceRef,
    build_workspace_plan,
    prepare_workspace,
    read_workspace_ref,
    write_workspace_json,
)


def run_git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr or result.stdout)
    return result


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def init_repo(tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    run_git(repo_root, "init")
    run_git(repo_root, "config", "user.name", "Test User")
    run_git(repo_root, "config", "user.email", "test@example.com")
    return repo_root


def commit_initial_tree(repo_root: Path) -> None:
    run_git(repo_root, "add", ".")
    run_git(repo_root, "commit", "-m", "initial commit")


def test_clean_repo_builds_git_worktree_plan(tmp_path: Path) -> None:
    repo_root = init_repo(tmp_path)
    write_file(repo_root / "src" / "app.py", "print('hello')\n")
    write_file(repo_root / ".gitignore", "runs/\nvenv/\n.pytest_cache/\n")
    commit_initial_tree(repo_root)

    workspace_root = tmp_path / "runs" / "run-1" / "workspace"
    plan = build_workspace_plan(source_root=repo_root, workspace_root=workspace_root)

    assert plan["workspace"]["mode"] == WORKTREE_MODE
    assert plan["workspace"]["source_dirty"] is False
    assert plan["workspace"]["base_ref"] == run_git(repo_root, "rev-parse", "--short", "HEAD").stdout.strip()
    assert plan["materialization"]["git_worktree_command"] == [
        "git",
        "-C",
        str(repo_root),
        "worktree",
        "add",
        "--force",
        "--detach",
        str(workspace_root),
        plan["workspace"]["base_ref"],
    ]
    assert plan["materialization"]["snapshot_paths"] == []


def test_dirty_repo_snapshot_excludes_runtime_dirs_and_tracked_runs(tmp_path: Path) -> None:
    repo_root = init_repo(tmp_path)
    write_file(repo_root / ".gitignore", "ignored-runtime/\n*.tmp\nruns/\nvenv/\n.pytest_cache/\n")
    write_file(repo_root / "src" / "app.py", "print('hello')\n")
    write_file(repo_root / "docs" / "notes.md", "tracked notes\n")
    write_file(repo_root / "runs" / "README.md", "workspace notes\n")
    write_file(repo_root / "ignored-runtime" / "cache.tmp", "ignore me\n")
    write_file(repo_root / "venv" / "tool.txt", "ignore me\n")
    write_file(repo_root / ".pytest_cache" / "state", "ignore me\n")
    write_file(repo_root / "scratch.tmp", "ignore me\n")
    run_git(repo_root, "add", "-f", "runs/README.md")
    run_git(repo_root, "add", ".")
    run_git(repo_root, "commit", "-m", "initial commit")

    write_file(repo_root / "src" / "app.py", "print('changed')\n")
    write_file(repo_root / "docs" / "notes.md", "tracked notes updated\n")
    write_file(repo_root / "new-file.txt", "untracked file\n")

    workspace_root = tmp_path / "runs" / "run-2" / "workspace"
    plan = build_workspace_plan(source_root=repo_root, workspace_root=workspace_root)

    assert plan["workspace"]["mode"] == SNAPSHOT_MODE
    assert plan["workspace"]["source_dirty"] is True
    assert "src/app.py" in plan["materialization"]["snapshot_paths"]
    assert "docs/notes.md" in plan["materialization"]["snapshot_paths"]
    assert "new-file.txt" in plan["materialization"]["snapshot_paths"]
    assert "runs/README.md" not in plan["materialization"]["snapshot_paths"]
    assert "venv/tool.txt" not in plan["materialization"]["snapshot_paths"]
    assert ".pytest_cache/state" not in plan["materialization"]["snapshot_paths"]
    assert "ignored-runtime/cache.tmp" not in plan["materialization"]["snapshot_paths"]
    assert "scratch.tmp" not in plan["materialization"]["snapshot_paths"]

    materialized = prepare_workspace(source_root=repo_root, workspace_root=workspace_root)
    assert materialized["materialized"]["mode"] == SNAPSHOT_MODE
    assert materialized["materialized"]["runtime_prune"]["removed_paths"] == ["runs"]
    assert (workspace_root / ".git").exists()
    assert (workspace_root / "src" / "app.py").read_text(encoding="utf-8") == "print('changed')\n"
    assert (workspace_root / "docs" / "notes.md").read_text(encoding="utf-8") == "tracked notes updated\n"
    assert (workspace_root / "new-file.txt").read_text(encoding="utf-8") == "untracked file\n"
    assert not (workspace_root / "runs" / "README.md").exists()
    assert not (workspace_root / "venv").exists()
    assert not (workspace_root / ".pytest_cache").exists()


def test_workspace_json_roundtrip_preserves_workspace_ref(tmp_path: Path) -> None:
    repo_root = init_repo(tmp_path)
    write_file(repo_root / "src" / "app.py", "print('hello')\n")
    commit_initial_tree(repo_root)

    workspace_root = tmp_path / "runs" / "run-3" / "workspace"
    workspace = WorkspaceRef(
        mode=WORKTREE_MODE,
        root_path=str(workspace_root),
        base_ref="abc1234",
        source_dirty=False,
        cleanup_policy="keep_on_failure",
    )

    workspace_json_path = write_workspace_json(tmp_path / "runs" / "run-3", workspace=workspace, plan={"kind": "demo"})
    payload = json.loads(workspace_json_path.read_text(encoding="utf-8"))

    assert payload["workspace"] == workspace.to_dict()
    assert payload["plan"] == {"kind": "demo"}
    assert read_workspace_ref(tmp_path / "runs" / "run-3") == workspace
