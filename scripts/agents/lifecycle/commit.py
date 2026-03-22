#!/usr/bin/env python3
"""Фиксирует commit-stage внутри run bundle и опционально создает git commit."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .apply import collect_git_snapshot, file_presence_summary
from .approve import COMMIT_ID, PUSH_ID
from .execute import DEFAULT_RUNS_DIR
from scripts.agents.workspace import resolve_workspace_root
from scripts.config import ROOT


def load_json(path: Path) -> dict[str, Any]:
    """Читает JSON-файл."""
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    """Записывает JSON-файл."""
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def clone_json_compatible(payload: Any) -> Any:
    """Делает безопасную глубокую копию JSON-совместимого объекта."""
    return json.loads(json.dumps(payload, ensure_ascii=False))


def normalize_rel_path(value: str) -> str:
    """Нормализует относительный путь."""
    return value.strip().replace("\\", "/").lstrip("./")


def resolve_run_dir(args: argparse.Namespace) -> Path:
    """Определяет директорию запуска."""
    if args.run_dir and args.run_id:
        raise ValueError("Нельзя одновременно использовать --run-dir и --run-id")
    if args.run_dir:
        return ROOT / normalize_rel_path(args.run_dir)
    if args.run_id:
        return (ROOT / normalize_rel_path(args.runs_dir)) / args.run_id.strip()
    raise ValueError("Нужно указать либо --run-dir, либо --run-id")


def read_message(args: argparse.Namespace, run_summary: dict[str, Any]) -> str:
    """Считывает или генерирует commit message."""
    if args.message and args.message_file:
        raise ValueError("Нельзя одновременно использовать --message и --message-file")
    if args.message_file:
        message = Path(args.message_file).read_text(encoding="utf-8").strip()
    else:
        message = (args.message or "").strip()

    if message:
        return message

    task_type = run_summary.get("task_type", {}).get("id", "task")
    changed_paths = run_summary.get("changed_paths", [])
    if changed_paths:
        return f"chore: apply {task_type} updates"
    return "chore: record approved changes"


def read_commit_files(args: argparse.Namespace, run_summary: dict[str, Any]) -> list[str]:
    """Определяет набор файлов для commit-stage."""
    paths: list[str] = []
    if args.file:
        paths.extend(args.file)
    if args.files_file:
        raw_lines = Path(args.files_file).read_text(encoding="utf-8").splitlines()
        paths.extend(line for line in raw_lines if line.strip())

    normalized = [normalize_rel_path(item) for item in paths if item.strip()]
    if normalized:
        return normalized

    implementation = run_summary.get("implementation", {})
    applied_files = implementation.get("applied_files", [])
    if applied_files:
        return [normalize_rel_path(item) for item in applied_files if str(item).strip()]

    changed_paths = run_summary.get("changed_paths", [])
    if changed_paths:
        return [normalize_rel_path(item) for item in changed_paths if str(item).strip()]

    raise ValueError("Не удалось определить commit files: передайте --file или заполните changed_paths")


def checkpoint_status_map(approval_payload: dict[str, Any]) -> dict[str, str]:
    """Возвращает map checkpoint_id -> status."""
    return {
        item["id"]: item.get("status", "unknown")
        for item in approval_payload.get("checkpoints", [])
    }


def ensure_commit_allowed(run_summary: dict[str, Any], approval_payload: dict[str, Any]) -> None:
    """Проверяет, что lifecycle допускает commit-stage."""
    statuses = checkpoint_status_map(approval_payload)
    if statuses.get(COMMIT_ID) != "approved":
        raise ValueError("Commit-stage требует approve checkpoint 'commit'")

    allowed_statuses = {
        "commit_approved_pending_execution",
        "approved_for_push_decision",
        "awaiting_push_approval",
        "push_approved_pending_execution",
        "commit_created_pending_push_decision",
    }
    allowed_next_actions = {
        "create_commit",
        "decide_on_push",
        "await_push_approval",
        "execute_push",
    }

    if (
        run_summary.get("status") not in allowed_statuses
        and run_summary.get("next_action") not in allowed_next_actions
    ):
        raise ValueError("Commit-stage можно запускать только после commit approval")


def run_git_command(args: list[str], paths: list[str] | None = None, *, repo_root: Path = ROOT) -> subprocess.CompletedProcess[str]:
    """Запускает git-команду в корне репозитория."""
    command = ["git", "-C", str(repo_root), *args]
    if paths:
        command.append("--")
        command.extend(paths)
    return subprocess.run(
        command,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def create_commit(message: str, files: list[str], *, repo_root: Path) -> tuple[str, str]:
    """Создает git commit только по указанным файлам."""
    add_result = run_git_command(["add"], files, repo_root=repo_root)
    if add_result.returncode != 0:
        raise ValueError(f"Не удалось выполнить git add: {add_result.stderr.strip() or add_result.stdout.strip()}")

    commit_result = run_git_command(["commit", "-m", message], files, repo_root=repo_root)
    if commit_result.returncode != 0:
        raise ValueError(
            f"Не удалось выполнить git commit: {commit_result.stderr.strip() or commit_result.stdout.strip()}",
        )

    rev_result = run_git_command(["rev-parse", "HEAD"], repo_root=repo_root)
    if rev_result.returncode != 0:
        raise ValueError(
            f"Commit создан, но не удалось получить hash: {rev_result.stderr.strip() or rev_result.stdout.strip()}",
        )

    return rev_result.stdout.strip(), commit_result.stdout.strip()


def derive_status_and_next_action(push_status: str, *, execute: bool) -> tuple[str, str]:
    """Определяет status и next_action после commit-stage."""
    if not execute:
        return "commit_approved_pending_execution", "create_commit"
    if push_status == "approved":
        return "push_approved_pending_execution", "execute_push"
    return "commit_created_pending_push_decision", "decide_on_push"


def build_commit_result(
    *,
    run_summary: dict[str, Any],
    message: str,
    files: list[str],
    committed_by: str,
    execute: bool,
    git_snapshot: dict[str, Any],
    file_presence: dict[str, list[str]],
    commit_hash: str | None,
    commit_stdout: str,
) -> dict[str, Any]:
    """Строит commit-result.json."""
    return {
        "version": 1,
        "run_id": run_summary["run_id"],
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "committed_by": committed_by,
        "mode": "execute" if execute else "dry_run",
        "message": message,
        "files": files,
        "file_presence": file_presence,
        "git": {
            "diff_summary": git_snapshot["diff_summary"],
            "status_entries": git_snapshot["status_entries"],
            "warnings": git_snapshot["warnings"],
        },
        "commit_created": bool(commit_hash),
        "commit_hash": commit_hash,
        "git_commit_stdout": commit_stdout,
    }


def update_execution_state(
    execution_state: dict[str, Any] | None,
    *,
    status: str,
    next_action: str,
    commit_result: dict[str, Any],
) -> dict[str, Any] | None:
    """Обновляет execution-state.json, если он существует."""
    if execution_state is None:
        return None

    updated = clone_json_compatible(execution_state)
    updated["phase"] = "commit_recorded" if commit_result["commit_created"] else "commit_prepared"
    updated["status"] = status
    updated["next_action"] = next_action
    updated["commit"] = {
        "mode": commit_result["mode"],
        "message": commit_result["message"],
        "files": commit_result["files"],
        "commit_created": commit_result["commit_created"],
        "commit_hash": commit_result["commit_hash"],
    }
    return updated


def build_output(
    run_dir: Path,
    *,
    message: str,
    files: list[str],
    committed_by: str,
    execute: bool,
) -> dict[str, Any]:
    """Фиксирует commit-stage и опционально создает commit."""
    summary_path = run_dir / "run-summary.json"
    approval_path = run_dir / "approval-checkpoints.json"
    execution_state_path = run_dir / "execution-state.json"
    commit_result_path = run_dir / "commit-result.json"
    commit_message_path = run_dir / "commit-message.txt"

    if not summary_path.is_file():
        raise FileNotFoundError(f"Не найден файл: {summary_path}")
    if not approval_path.is_file():
        raise FileNotFoundError(f"Не найден файл: {approval_path}")

    run_summary = load_json(summary_path)
    approval_payload = load_json(approval_path)
    execution_state = load_json(execution_state_path) if execution_state_path.is_file() else None

    ensure_commit_allowed(run_summary, approval_payload)
    repo_root = resolve_workspace_root(run_dir / "workspace.json", fallback=ROOT)
    file_presence = file_presence_summary(files, repo_root=repo_root)
    git_snapshot = collect_git_snapshot(files, repo_root=repo_root)
    if execute and git_snapshot["diff_summary"]["file_count"] == 0:
        raise ValueError("Нечего коммитить: git diff по указанным файлам пуст")

    commit_hash: str | None = None
    commit_stdout = ""
    if execute:
        commit_hash, commit_stdout = create_commit(message, files, repo_root=repo_root)

    commit_result = build_commit_result(
        run_summary=run_summary,
        message=message,
        files=files,
        committed_by=committed_by,
        execute=execute,
        git_snapshot=git_snapshot,
        file_presence=file_presence,
        commit_hash=commit_hash,
        commit_stdout=commit_stdout,
    )

    push_status = checkpoint_status_map(approval_payload).get(PUSH_ID, "awaiting_approval")
    status, next_action = derive_status_and_next_action(push_status, execute=execute)
    updated_execution_state = update_execution_state(
        execution_state,
        status=status,
        next_action=next_action,
        commit_result=commit_result,
    )

    artifacts = run_summary.setdefault("artifacts", {})
    artifacts["commit_result"] = str(commit_result_path.relative_to(ROOT)).replace("\\", "/")
    artifacts["commit_message"] = str(commit_message_path.relative_to(ROOT)).replace("\\", "/")

    run_summary["status"] = status
    run_summary["next_action"] = next_action
    run_summary["artifacts"] = artifacts
    run_summary["commit"] = {
        "mode": commit_result["mode"],
        "message": message,
        "files": files,
        "commit_created": bool(commit_hash),
        "commit_hash": commit_hash,
    }

    write_json(commit_result_path, commit_result)
    commit_message_path.write_text(message + "\n", encoding="utf-8")
    if updated_execution_state is not None:
        write_json(execution_state_path, updated_execution_state)
    write_json(summary_path, run_summary)

    return {
        "run_id": run_summary["run_id"],
        "run_dir": str(run_dir.relative_to(ROOT)).replace("\\", "/"),
        "status": status,
        "next_action": next_action,
        "mode": commit_result["mode"],
        "commit_created": commit_result["commit_created"],
        "commit_hash": commit_hash,
        "artifacts": {
            "commit_result": artifacts["commit_result"],
            "commit_message": artifacts["commit_message"],
        },
    }


def parse_args() -> argparse.Namespace:
    """Парсит аргументы CLI."""
    parser = argparse.ArgumentParser(
        description="Фиксация commit-stage и опциональное создание git commit.",
    )
    parser.add_argument("--run-dir", help="Путь к директории run bundle.")
    parser.add_argument("--run-id", help="Идентификатор запуска внутри runs-dir.")
    parser.add_argument(
        "--runs-dir",
        default=str(DEFAULT_RUNS_DIR.relative_to(ROOT)).replace("\\", "/"),
        help="Базовая директория запусков (по умолчанию: runs).",
    )
    parser.add_argument("--message", default="", help="Commit message.")
    parser.add_argument("--message-file", help="Путь к файлу с commit message.")
    parser.add_argument(
        "--file",
        action="append",
        help="Файл для commit-stage. Можно передавать несколько раз.",
    )
    parser.add_argument("--files-file", help="Путь к файлу со списком commit files, по одному на строку.")
    parser.add_argument("--committed-by", default="release_manager", help="Кто зафиксировал commit-stage.")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Реально выполнить git add/git commit. Без флага работает только запись dry-run артефактов.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Печатать JSON с отступами.",
    )
    return parser.parse_args()


def main() -> int:
    """Точка входа CLI."""
    args = parse_args()
    try:
        run_dir = resolve_run_dir(args)
        summary_path = run_dir / "run-summary.json"
        if not summary_path.is_file():
            raise FileNotFoundError(f"Не найден файл: {summary_path}")
        run_summary = load_json(summary_path)
        result = build_output(
            run_dir,
            message=read_message(args, run_summary),
            files=read_commit_files(args, run_summary),
            committed_by=args.committed_by.strip() or "release_manager",
            execute=args.execute,
        )
    except (FileNotFoundError, ValueError) as exc:
        json.dump(
            {"error": str(exc)},
            sys.stdout,
            ensure_ascii=False,
            indent=2 if args.pretty else None,
        )
        if args.pretty:
            sys.stdout.write("\n")
        return 1

    json.dump(
        result,
        sys.stdout,
        ensure_ascii=False,
        indent=2 if args.pretty else None,
    )
    if args.pretty:
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
