#!/usr/bin/env python3
"""Фиксирует apply-stage внутри run bundle после внесения изменений."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .execute import DEFAULT_RUNS_DIR
from scripts.config import ROOT


IMPLEMENT_STEP_ID = "implement_change"
VERIFY_STEP_ID = "verify_change"
SANDBOX_STEP_ID = "run_in_sandbox"
REVIEW_STEP_ID = "review_result"
REQUEST_APPROVAL_STEP_ID = "request_approval"


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


def read_summary(args: argparse.Namespace) -> str:
    """Считывает implementation summary."""
    if args.summary and args.summary_file:
        raise ValueError("Нельзя одновременно использовать --summary и --summary-file")
    if args.summary_file:
        return Path(args.summary_file).read_text(encoding="utf-8").strip()
    return (args.summary or "").strip()


def read_explicit_paths(args: argparse.Namespace) -> list[str]:
    """Считывает явный список измененных путей."""
    paths: list[str] = []
    if args.file:
        paths.extend(args.file)
    if args.files_file:
        raw_lines = Path(args.files_file).read_text(encoding="utf-8").splitlines()
        paths.extend(line for line in raw_lines if line.strip())
    return [normalize_rel_path(item) for item in paths if item.strip()]


def step_exists(plan_payload: dict[str, Any], step_id: str) -> bool:
    """Проверяет наличие шага в plan.json."""
    return any(step.get("id") == step_id for step in plan_payload.get("plan", []))


def checkpoint_status_map(approval_payload: dict[str, Any]) -> dict[str, str]:
    """Возвращает map checkpoint_id -> status."""
    return {
        item["id"]: item.get("status", "unknown")
        for item in approval_payload.get("checkpoints", [])
    }


def ensure_apply_allowed(run_summary: dict[str, Any], plan_payload: dict[str, Any]) -> None:
    """Проверяет, что lifecycle допускает apply-stage."""
    if not step_exists(plan_payload, IMPLEMENT_STEP_ID):
        raise ValueError("В plan.json отсутствует шаг implement_change")

    approval_payload = run_summary.get("approval", {})
    run_checks_status = checkpoint_status_map(approval_payload).get("run_checks", "awaiting_approval")

    allowed_statuses = {
        "context_loaded",
        "approved_for_implementation",
    }
    allowed_next_actions = {"implement_change"}

    if (
        run_summary.get("status") not in allowed_statuses
        and run_summary.get("next_action") not in allowed_next_actions
    ):
        raise ValueError(
            "Apply-stage можно запускать только когда run готов к implement_change",
        )
    if run_checks_status not in {"approved", "not_required"}:
        raise ValueError("Apply-stage требует завершенный pre-implementation checkpoint 'run_checks'")


def resolve_applied_files(
    explicit_paths: list[str],
    run_summary: dict[str, Any],
) -> list[str]:
    """Определяет, какие файлы считать примененными."""
    if explicit_paths:
        return explicit_paths

    fallback_paths = [normalize_rel_path(item) for item in run_summary.get("changed_paths", []) if str(item).strip()]
    if fallback_paths:
        return fallback_paths

    raise ValueError("Не удалось определить applied files: передайте --file или заполните changed_paths")


def file_presence_summary(paths: list[str]) -> dict[str, list[str]]:
    """Показывает, какие из applied files реально существуют в workspace."""
    existing: list[str] = []
    missing: list[str] = []

    for rel_path in paths:
        if (ROOT / rel_path).exists():
            existing.append(rel_path)
        else:
            missing.append(rel_path)

    return {
        "existing": existing,
        "missing": missing,
    }


def run_git_command(args: list[str], paths: list[str]) -> subprocess.CompletedProcess[str]:
    """Запускает git-команду в корне репозитория."""
    command = ["git", "-C", str(ROOT), *args]
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


def parse_git_status(stdout: str) -> list[dict[str, str]]:
    """Парсит git status --porcelain=v1."""
    entries: list[dict[str, str]] = []
    for raw_line in stdout.splitlines():
        if len(raw_line) < 4:
            continue
        status_code = raw_line[:2]
        path = raw_line[3:].strip().replace("\\", "/")
        entries.append(
            {
                "status": status_code,
                "path": path,
            }
        )
    return entries


def parse_numstat(stdout: str) -> dict[str, Any]:
    """Парсит git diff --numstat."""
    files: list[dict[str, Any]] = []
    added_total = 0
    deleted_total = 0

    for raw_line in stdout.splitlines():
        parts = raw_line.split("\t")
        if len(parts) != 3:
            continue
        added, deleted, path = parts
        normalized_path = path.replace("\\", "/")
        file_entry: dict[str, Any] = {"path": normalized_path}
        if added.isdigit():
            file_entry["added"] = int(added)
            added_total += int(added)
        else:
            file_entry["added"] = added
        if deleted.isdigit():
            file_entry["deleted"] = int(deleted)
            deleted_total += int(deleted)
        else:
            file_entry["deleted"] = deleted
        files.append(file_entry)

    return {
        "files": files,
        "file_count": len(files),
        "added_lines": added_total,
        "deleted_lines": deleted_total,
    }


def merge_numstat_summaries(*summaries: dict[str, Any]) -> dict[str, Any]:
    """Объединяет несколько numstat summary в один итог."""
    merged_by_path: dict[str, dict[str, Any]] = {}

    for summary in summaries:
        for entry in summary.get("files", []):
            path = entry["path"]
            current = merged_by_path.setdefault(
                path,
                {
                    "path": path,
                    "added": 0,
                    "deleted": 0,
                },
            )
            if isinstance(entry.get("added"), int) and isinstance(current.get("added"), int):
                current["added"] += entry["added"]
            else:
                current["added"] = entry.get("added")
            if isinstance(entry.get("deleted"), int) and isinstance(current.get("deleted"), int):
                current["deleted"] += entry["deleted"]
            else:
                current["deleted"] = entry.get("deleted")

    merged_files = list(merged_by_path.values())
    return {
        "files": merged_files,
        "file_count": len(merged_files),
        "added_lines": sum(entry["added"] for entry in merged_files if isinstance(entry.get("added"), int)),
        "deleted_lines": sum(entry["deleted"] for entry in merged_files if isinstance(entry.get("deleted"), int)),
    }


def collect_git_snapshot(paths: list[str]) -> dict[str, Any]:
    """Снимает git snapshot по выбранным файлам."""
    status_proc = run_git_command(["status", "--short"], paths)
    working_diff_proc = run_git_command(["diff"], paths)
    staged_diff_proc = run_git_command(["diff", "--cached"], paths)
    working_numstat_proc = run_git_command(["diff", "--numstat"], paths)
    staged_numstat_proc = run_git_command(["diff", "--cached", "--numstat"], paths)

    warnings: list[str] = []
    if status_proc.returncode != 0:
        warnings.append("git_status_command_failed")
    if working_diff_proc.returncode != 0:
        warnings.append("git_working_diff_command_failed")
    if staged_diff_proc.returncode != 0:
        warnings.append("git_staged_diff_command_failed")
    if working_numstat_proc.returncode != 0:
        warnings.append("git_working_numstat_command_failed")
    if staged_numstat_proc.returncode != 0:
        warnings.append("git_staged_numstat_command_failed")

    status_entries = parse_git_status(status_proc.stdout) if status_proc.returncode == 0 else []
    working_summary = parse_numstat(working_numstat_proc.stdout) if working_numstat_proc.returncode == 0 else {
        "files": [],
        "file_count": 0,
        "added_lines": 0,
        "deleted_lines": 0,
    }
    staged_summary = parse_numstat(staged_numstat_proc.stdout) if staged_numstat_proc.returncode == 0 else {
        "files": [],
        "file_count": 0,
        "added_lines": 0,
        "deleted_lines": 0,
    }
    diff_summary = merge_numstat_summaries(working_summary, staged_summary)

    untracked_paths = [
        entry["path"]
        for entry in status_entries
        if entry["status"].strip() == "??"
    ]
    if untracked_paths:
        warnings.append("untracked_files_will_not_appear_in_git_diff")

    return {
        "status_entries": status_entries,
        "diff_text": build_combined_diff_text(
            working_diff_proc.stdout if working_diff_proc.returncode == 0 else "",
            staged_diff_proc.stdout if staged_diff_proc.returncode == 0 else "",
        ),
        "diff_summary": diff_summary,
        "warnings": warnings,
    }


def build_combined_diff_text(working_diff_text: str, staged_diff_text: str) -> str:
    """Собирает объединенный diff-текст для артефакта."""
    sections: list[str] = []
    if staged_diff_text.strip():
        sections.append("# Staged Diff\n\n" + staged_diff_text.strip() + "\n")
    if working_diff_text.strip():
        sections.append("# Working Tree Diff\n\n" + working_diff_text.strip() + "\n")
    return "\n".join(sections)


def write_optional_text(path: Path, text: str) -> bool:
    """Записывает текстовый артефакт, если есть содержимое."""
    if not text.strip():
        return False
    path.write_text(text, encoding="utf-8")
    return True


def select_next_stage(plan_payload: dict[str, Any]) -> tuple[str, str]:
    """Определяет следующий шаг lifecycle после apply-stage."""
    step_ids = [step.get("id") for step in plan_payload.get("plan", [])]
    if VERIFY_STEP_ID in step_ids:
        return "changes_applied_pending_verification", "verify_change"
    if SANDBOX_STEP_ID in step_ids:
        return "changes_applied_pending_sandbox", "run_in_sandbox"
    if REVIEW_STEP_ID in step_ids:
        return "changes_applied_pending_review", "review_result"
    if REQUEST_APPROVAL_STEP_ID in step_ids:
        return "changes_applied_pending_approval", "request_approval"
    return "changes_applied", "review_result"


def update_plan_for_apply(plan_payload: dict[str, Any]) -> dict[str, Any]:
    """Помечает implement_change как завершенный."""
    updated = clone_json_compatible(plan_payload)
    for step in updated.get("plan", []):
        if step.get("id") == IMPLEMENT_STEP_ID:
            step["status"] = "completed"
    return updated


def build_apply_result(
    *,
    run_summary: dict[str, Any],
    applied_files: list[str],
    summary_text: str,
    applied_by: str,
    git_snapshot: dict[str, Any],
    file_presence: dict[str, list[str]],
    diff_artifact_written: bool,
) -> dict[str, Any]:
    """Строит apply-result.json."""
    return {
        "version": 1,
        "run_id": run_summary["run_id"],
        "applied_at_utc": datetime.now(timezone.utc).isoformat(),
        "applied_by": applied_by,
        "summary": summary_text,
        "applied_files": applied_files,
        "file_presence": file_presence,
        "git": {
            "status_entries": git_snapshot["status_entries"],
            "diff_summary": git_snapshot["diff_summary"],
            "warnings": git_snapshot["warnings"],
            "diff_artifact_written": diff_artifact_written,
        },
    }


def update_execution_state(
    execution_state: dict[str, Any] | None,
    *,
    status: str,
    next_action: str,
    apply_result: dict[str, Any],
) -> dict[str, Any] | None:
    """Обновляет execution-state.json, если он существует."""
    if execution_state is None:
        return None

    updated = clone_json_compatible(execution_state)
    updated["phase"] = "changes_applied"
    updated["status"] = status
    updated["next_action"] = next_action
    updated["applied_at_utc"] = apply_result["applied_at_utc"]
    updated["implementation"] = {
        "applied_by": apply_result["applied_by"],
        "summary": apply_result["summary"],
        "applied_files": apply_result["applied_files"],
        "file_presence": apply_result["file_presence"],
        "git": apply_result["git"],
    }
    return updated


def build_output(
    run_dir: Path,
    *,
    explicit_paths: list[str],
    summary_text: str,
    applied_by: str,
    allow_empty_diff: bool,
) -> dict[str, Any]:
    """Фиксирует apply-stage и обновляет run bundle."""
    summary_path = run_dir / "run-summary.json"
    plan_path = run_dir / "plan.json"
    execution_state_path = run_dir / "execution-state.json"
    apply_result_path = run_dir / "apply-result.json"
    diff_artifact_path = run_dir / "workspace-diff.patch"

    if not summary_path.is_file():
        raise FileNotFoundError(f"Не найден файл: {summary_path}")
    if not plan_path.is_file():
        raise FileNotFoundError(f"Не найден файл: {plan_path}")

    run_summary = load_json(summary_path)
    plan_payload = load_json(plan_path)
    execution_state = load_json(execution_state_path) if execution_state_path.is_file() else None

    ensure_apply_allowed(run_summary, plan_payload)
    applied_files = resolve_applied_files(explicit_paths, run_summary)
    file_presence = file_presence_summary(applied_files)
    git_snapshot = collect_git_snapshot(applied_files)
    if not allow_empty_diff and git_snapshot["diff_summary"]["file_count"] == 0:
        raise ValueError(
            "Apply-stage требует непустой git diff по указанным файлам. "
            "Если нужно зафиксировать apply без diff осознанно, передайте --allow-empty-diff",
        )

    diff_artifact_written = write_optional_text(diff_artifact_path, git_snapshot["diff_text"])
    apply_result = build_apply_result(
        run_summary=run_summary,
        applied_files=applied_files,
        summary_text=summary_text,
        applied_by=applied_by,
        git_snapshot=git_snapshot,
        file_presence=file_presence,
        diff_artifact_written=diff_artifact_written,
    )

    updated_plan = update_plan_for_apply(plan_payload)
    status, next_action = select_next_stage(updated_plan)
    updated_execution_state = update_execution_state(
        execution_state,
        status=status,
        next_action=next_action,
        apply_result=apply_result,
    )

    artifacts = run_summary.setdefault("artifacts", {})
    artifacts["apply_result"] = str(apply_result_path.relative_to(ROOT)).replace("\\", "/")
    if diff_artifact_written:
        artifacts["workspace_diff"] = str(diff_artifact_path.relative_to(ROOT)).replace("\\", "/")
    elif "workspace_diff" in artifacts:
        artifacts.pop("workspace_diff")

    run_summary["status"] = status
    run_summary["next_action"] = next_action
    run_summary["artifacts"] = artifacts
    run_summary["implementation"] = {
        "applied_by": applied_by,
        "summary": summary_text,
        "applied_files": applied_files,
        "git_diff_files": apply_result["git"]["diff_summary"]["file_count"],
        "git_warnings": apply_result["git"]["warnings"],
    }

    write_json(apply_result_path, apply_result)
    write_json(plan_path, updated_plan)
    if updated_execution_state is not None:
        write_json(execution_state_path, updated_execution_state)
    write_json(summary_path, run_summary)

    return {
        "run_id": run_summary["run_id"],
        "run_dir": str(run_dir.relative_to(ROOT)).replace("\\", "/"),
        "status": status,
        "next_action": next_action,
        "applied_files": applied_files,
        "diff_summary": apply_result["git"]["diff_summary"],
        "warnings": apply_result["git"]["warnings"],
        "artifacts": {
            "apply_result": artifacts["apply_result"],
            "workspace_diff": artifacts.get("workspace_diff"),
        },
    }


def parse_args() -> argparse.Namespace:
    """Парсит аргументы CLI."""
    parser = argparse.ArgumentParser(
        description="Фиксация apply-stage и запись implementation artifacts в run bundle.",
    )
    parser.add_argument("--run-dir", help="Путь к директории run bundle.")
    parser.add_argument("--run-id", help="Идентификатор запуска внутри runs-dir.")
    parser.add_argument(
        "--runs-dir",
        default=str(DEFAULT_RUNS_DIR.relative_to(ROOT)).replace("\\", "/"),
        help="Базовая директория запусков (по умолчанию: local/runs).",
    )
    parser.add_argument(
        "--file",
        action="append",
        help="Файл, который нужно включить в apply-stage. Можно передавать несколько раз.",
    )
    parser.add_argument("--files-file", help="Путь к файлу со списком applied files, по одному на строку.")
    parser.add_argument("--summary", default="", help="Короткое описание внесенных изменений.")
    parser.add_argument("--summary-file", help="Путь к файлу с описанием внесенных изменений.")
    parser.add_argument("--applied-by", default="coder", help="Кто применил изменения в рамках run.")
    parser.add_argument(
        "--allow-empty-diff",
        action="store_true",
        help="Разрешить apply-stage даже если git diff по выбранным файлам пуст.",
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
        result = build_output(
            run_dir,
            explicit_paths=read_explicit_paths(args),
            summary_text=read_summary(args),
            applied_by=args.applied_by.strip() or "coder",
            allow_empty_diff=args.allow_empty_diff,
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
