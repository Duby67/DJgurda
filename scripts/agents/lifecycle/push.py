#!/usr/bin/env python3
"""Фиксирует push-stage внутри run bundle и опционально выполняет git push."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .approve import PUSH_ID
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


def run_git_command(args: list[str], *, repo_root: Path = ROOT) -> subprocess.CompletedProcess[str]:
    """Запускает git-команду в корне репозитория."""
    command = ["git", "-C", str(repo_root), *args]
    return subprocess.run(
        command,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def checkpoint_status_map(approval_payload: dict[str, Any]) -> dict[str, str]:
    """Возвращает map checkpoint_id -> status."""
    return {
        item["id"]: item.get("status", "unknown")
        for item in approval_payload.get("checkpoints", [])
    }


def ensure_push_allowed(run_summary: dict[str, Any], approval_payload: dict[str, Any]) -> None:
    """Проверяет, что lifecycle допускает push-stage."""
    statuses = checkpoint_status_map(approval_payload)
    if statuses.get(PUSH_ID) != "approved":
        raise ValueError("Push-stage требует approve checkpoint 'push'")
    if not run_summary.get("commit", {}).get("commit_created", False):
        raise ValueError("Push-stage требует ранее созданный реальный commit")

    allowed_statuses = {
        "push_approved_pending_execution",
        "push_executed",
        "push_failed",
        "push_blocked",
    }
    allowed_next_actions = {
        "execute_push",
        "review_push_failure",
        "resolve_push_blockers",
        "run_complete",
    }

    if (
        run_summary.get("status") not in allowed_statuses
        and run_summary.get("next_action") not in allowed_next_actions
    ):
        raise ValueError("Push-stage можно запускать только после push approval")


def resolve_branch(args: argparse.Namespace, *, repo_root: Path) -> str:
    """Определяет branch для push."""
    if args.branch:
        return args.branch.strip()

    branch_result = run_git_command(["rev-parse", "--abbrev-ref", "HEAD"], repo_root=repo_root)
    if branch_result.returncode != 0:
        raise ValueError(
            f"Не удалось определить текущую ветку: {branch_result.stderr.strip() or branch_result.stdout.strip()}",
        )

    branch = branch_result.stdout.strip()
    if not branch or branch == "HEAD":
        raise ValueError("Текущая ветка не определена. Передайте --branch явно")
    return branch


def execute_push(remote: str, branch: str, *, repo_root: Path) -> str:
    """Выполняет git push HEAD в указанную ветку remote."""
    push_result = run_git_command(["push", remote, f"HEAD:{branch}"], repo_root=repo_root)
    if push_result.returncode != 0:
        raise ValueError(
            f"Не удалось выполнить git push: {push_result.stderr.strip() or push_result.stdout.strip()}",
        )
    return push_result.stdout.strip()


def derive_status_and_next_action(*, execute: bool) -> tuple[str, str]:
    """Определяет status и next_action после push-stage."""
    if not execute:
        return "push_approved_pending_execution", "execute_push"
    return "push_executed", "run_complete"


def build_push_result(
    *,
    run_summary: dict[str, Any],
    pushed_by: str,
    remote: str,
    branch: str,
    execute: bool,
    push_stdout: str,
) -> dict[str, Any]:
    """Строит push-result.json."""
    return {
        "version": 1,
        "run_id": run_summary["run_id"],
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "pushed_by": pushed_by,
        "mode": "execute" if execute else "dry_run",
        "remote": remote,
        "branch": branch,
        "push_created": execute,
        "git_push_stdout": push_stdout,
        "warnings": [],
    }


def update_execution_state(
    execution_state: dict[str, Any] | None,
    *,
    status: str,
    next_action: str,
    push_result: dict[str, Any],
) -> dict[str, Any] | None:
    """Обновляет execution-state.json, если он существует."""
    if execution_state is None:
        return None

    updated = clone_json_compatible(execution_state)
    updated["phase"] = "push_recorded" if push_result["push_created"] else "push_prepared"
    updated["status"] = status
    updated["next_action"] = next_action
    updated["push"] = {
        "mode": push_result["mode"],
        "remote": push_result["remote"],
        "branch": push_result["branch"],
        "push_created": push_result["push_created"],
    }
    return updated


def build_output(
    run_dir: Path,
    *,
    pushed_by: str,
    remote: str,
    branch: str,
    execute: bool,
) -> dict[str, Any]:
    """Фиксирует push-stage и опционально выполняет git push."""
    summary_path = run_dir / "run-summary.json"
    approval_path = run_dir / "approval-checkpoints.json"
    execution_state_path = run_dir / "execution-state.json"
    push_result_path = run_dir / "push-result.json"

    if not summary_path.is_file():
        raise FileNotFoundError(f"Не найден файл: {summary_path}")
    if not approval_path.is_file():
        raise FileNotFoundError(f"Не найден файл: {approval_path}")

    run_summary = load_json(summary_path)
    approval_payload = load_json(approval_path)
    execution_state = load_json(execution_state_path) if execution_state_path.is_file() else None

    ensure_push_allowed(run_summary, approval_payload)
    repo_root = resolve_workspace_root(run_dir / "workspace.json", fallback=ROOT)

    push_stdout = ""
    if execute:
        push_stdout = execute_push(remote, branch, repo_root=repo_root)

    push_result = build_push_result(
        run_summary=run_summary,
        pushed_by=pushed_by,
        remote=remote,
        branch=branch,
        execute=execute,
        push_stdout=push_stdout,
    )

    status, next_action = derive_status_and_next_action(execute=execute)
    updated_execution_state = update_execution_state(
        execution_state,
        status=status,
        next_action=next_action,
        push_result=push_result,
    )

    artifacts = run_summary.setdefault("artifacts", {})
    artifacts["push_result"] = str(push_result_path.relative_to(ROOT)).replace("\\", "/")

    run_summary["status"] = status
    run_summary["next_action"] = next_action
    run_summary["artifacts"] = artifacts
    run_summary["push_execution"] = {
        "mode": push_result["mode"],
        "remote": remote,
        "branch": branch,
        "push_created": execute,
    }

    write_json(push_result_path, push_result)
    if updated_execution_state is not None:
        write_json(execution_state_path, updated_execution_state)
    write_json(summary_path, run_summary)

    return {
        "run_id": run_summary["run_id"],
        "run_dir": str(run_dir.relative_to(ROOT)).replace("\\", "/"),
        "status": status,
        "next_action": next_action,
        "mode": push_result["mode"],
        "push_created": push_result["push_created"],
        "artifacts": {
            "push_result": artifacts["push_result"],
        },
    }


def parse_args() -> argparse.Namespace:
    """Парсит аргументы CLI."""
    parser = argparse.ArgumentParser(
        description="Фиксация push-stage и опциональное выполнение git push.",
    )
    parser.add_argument("--run-dir", help="Путь к директории run bundle.")
    parser.add_argument("--run-id", help="Идентификатор запуска внутри runs-dir.")
    parser.add_argument(
        "--runs-dir",
        default=str(DEFAULT_RUNS_DIR.relative_to(ROOT)).replace("\\", "/"),
        help="Базовая директория запусков (по умолчанию: runs).",
    )
    parser.add_argument("--remote", default="origin", help="Remote для push (по умолчанию: origin).")
    parser.add_argument("--branch", help="Целевая ветка для push. По умолчанию будет взята текущая.")
    parser.add_argument("--pushed-by", default="release_manager", help="Кто зафиксировал push-stage.")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Реально выполнить git push. Без флага работает только запись dry-run артефактов.",
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
        repo_root = resolve_workspace_root(run_dir / "workspace.json", fallback=ROOT)
        result = build_output(
            run_dir,
            pushed_by=args.pushed_by.strip() or "release_manager",
            remote=args.remote.strip() or "origin",
            branch=resolve_branch(args, repo_root=repo_root),
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
