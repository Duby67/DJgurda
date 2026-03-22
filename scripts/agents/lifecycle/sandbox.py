#!/usr/bin/env python3
"""Фиксирует sandbox-stage внутри run bundle после verification-stage."""

from __future__ import annotations

import argparse
import json
import shutil
import sys

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .apply import REQUEST_APPROVAL_STEP_ID, REVIEW_STEP_ID, SANDBOX_STEP_ID
from .execute import DEFAULT_RUNS_DIR
from scripts.config import ROOT


VALID_CONCLUSIONS = {"passed", "failed", "partial", "blocked", "skipped"}
VALID_CHECK_STATUSES = {"passed", "failed", "blocked", "skipped"}


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
    """Считывает sandbox summary."""
    if args.summary and args.summary_file:
        raise ValueError("Нельзя одновременно использовать --summary и --summary-file")
    if args.summary_file:
        return Path(args.summary_file).read_text(encoding="utf-8").strip()
    return (args.summary or "").strip()


def parse_check_result(raw_value: str) -> dict[str, str]:
    """Парсит строку формата sandbox-check=status|note."""
    if "=" not in raw_value:
        raise ValueError(
            "Каждый --check-result должен иметь формат check-id=status или check-id=status|note",
        )

    check_id, raw_rest = raw_value.split("=", 1)
    check_id = check_id.strip()
    if not check_id:
        raise ValueError("check-id не может быть пустым")

    status_text, separator, note = raw_rest.partition("|")
    status = status_text.strip().casefold()
    if status not in VALID_CHECK_STATUSES:
        raise ValueError(
            f"Неподдерживаемый status '{status}' в --check-result. Допустимо: {sorted(VALID_CHECK_STATUSES)}",
        )

    return {
        "id": check_id,
        "status": status,
        "note": note.strip() if separator else "",
    }


def read_checks(args: argparse.Namespace) -> list[dict[str, str]]:
    """Считывает sandbox checks из CLI или JSON-файла."""
    checks: list[dict[str, str]] = []

    if args.check_result:
        checks.extend(parse_check_result(item) for item in args.check_result)

    if args.checks_file:
        payload = json.loads(Path(args.checks_file).read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("--checks-file должен содержать JSON-массив объектов")
        for item in payload:
            if not isinstance(item, dict):
                raise ValueError("--checks-file должен содержать массив объектов")
            check_id = str(item.get("id", "")).strip()
            status = str(item.get("status", "")).strip().casefold()
            note = str(item.get("note", "")).strip()
            if not check_id:
                raise ValueError("Каждый check в --checks-file должен иметь непустой id")
            if status not in VALID_CHECK_STATUSES:
                raise ValueError(
                    f"Неподдерживаемый status '{status}' в --checks-file. Допустимо: {sorted(VALID_CHECK_STATUSES)}",
                )
            checks.append(
                {
                    "id": check_id,
                    "status": status,
                    "note": note,
                }
            )

    if not checks:
        raise ValueError("Нужно передать хотя бы один --check-result или --checks-file")

    seen: set[str] = set()
    unique_checks: list[dict[str, str]] = []
    for check in checks:
        if check["id"] in seen:
            raise ValueError(f"Повторяющийся check id: {check['id']}")
        seen.add(check["id"])
        unique_checks.append(check)
    return unique_checks


def read_path_list(args_value: list[str] | None, file_path: str | None) -> list[Path]:
    """Считывает список путей из аргументов и/или файла."""
    paths: list[Path] = []
    if args_value:
        paths.extend(Path(item) for item in args_value)
    if file_path:
        raw_lines = Path(file_path).read_text(encoding="utf-8").splitlines()
        paths.extend(Path(line.strip()) for line in raw_lines if line.strip())
    return paths


def step_exists(plan_payload: dict[str, Any], step_id: str) -> bool:
    """Проверяет наличие шага в plan.json."""
    return any(step.get("id") == step_id for step in plan_payload.get("plan", []))


def ensure_sandbox_allowed(run_summary: dict[str, Any], plan_payload: dict[str, Any]) -> None:
    """Проверяет, что lifecycle допускает sandbox-stage."""
    if not step_exists(plan_payload, SANDBOX_STEP_ID):
        raise ValueError("В plan.json отсутствует шаг run_in_sandbox")

    allowed_statuses = {
        "verification_recorded_pending_sandbox",
        "verification_partial_pending_sandbox",
        "verification_skipped_pending_sandbox",
        "sandbox_failed",
        "sandbox_blocked",
    }
    allowed_next_actions = {
        "run_in_sandbox",
        "review_sandbox_failures",
        "resolve_sandbox_blockers",
    }

    if (
        run_summary.get("status") not in allowed_statuses
        and run_summary.get("next_action") not in allowed_next_actions
    ):
        raise ValueError("Sandbox-stage можно запускать только после verification-stage")


def copy_files_to_run_dir(
    run_dir: Path,
    *,
    source_paths: list[Path],
    target_dir_name: str,
) -> list[dict[str, str]]:
    """Копирует список файлов в поддиректорию run bundle."""
    if not source_paths:
        return []

    target_dir = run_dir / target_dir_name
    target_dir.mkdir(parents=True, exist_ok=True)

    copied: list[dict[str, str]] = []
    used_names: set[str] = set()

    for source_path in source_paths:
        if not source_path.is_file():
            raise FileNotFoundError(f"Не найден файл: {source_path}")

        candidate_name = source_path.name
        suffix = 2
        while candidate_name in used_names:
            candidate_name = f"{source_path.stem}-{suffix}{source_path.suffix}"
            suffix += 1
        used_names.add(candidate_name)

        destination_path = target_dir / candidate_name
        shutil.copy2(source_path, destination_path)
        copied.append(
            {
                "source": str(source_path),
                "copied_to": str(destination_path.relative_to(ROOT)).replace("\\", "/"),
            }
        )

    return copied


def summarize_checks(checks: list[dict[str, str]]) -> dict[str, Any]:
    """Собирает агрегированную сводку по sandbox checks."""
    by_status: dict[str, int] = {}
    for check in checks:
        status = check["status"]
        by_status[status] = by_status.get(status, 0) + 1

    return {
        "total_checks": len(checks),
        "by_status": by_status,
    }


def derive_status_and_next_action(plan_payload: dict[str, Any], conclusion: str) -> tuple[str, str]:
    """Определяет новый status и next_action после sandbox-stage."""
    step_ids = [step.get("id") for step in plan_payload.get("plan", [])]

    if conclusion == "failed":
        return "sandbox_failed", "review_sandbox_failures"
    if conclusion == "blocked":
        return "sandbox_blocked", "resolve_sandbox_blockers"

    if REVIEW_STEP_ID in step_ids:
        prefix = "sandbox_skipped" if conclusion == "skipped" else "sandbox_recorded"
        if conclusion == "partial":
            prefix = "sandbox_partial"
        return f"{prefix}_pending_review", "review_result"
    if REQUEST_APPROVAL_STEP_ID in step_ids:
        prefix = "sandbox_skipped" if conclusion == "skipped" else "sandbox_recorded"
        if conclusion == "partial":
            prefix = "sandbox_partial"
        return f"{prefix}_pending_approval", "request_approval"

    return "sandbox_recorded", "review_result"


def update_plan_for_sandbox(plan_payload: dict[str, Any], conclusion: str) -> dict[str, Any]:
    """Обновляет шаг run_in_sandbox в plan.json."""
    updated = clone_json_compatible(plan_payload)
    status_by_conclusion = {
        "passed": "completed",
        "partial": "completed",
        "skipped": "completed",
        "failed": "failed",
        "blocked": "blocked",
    }

    for step in updated.get("plan", []):
        if step.get("id") == SANDBOX_STEP_ID:
            step["status"] = status_by_conclusion[conclusion]
    return updated


def build_sandbox_result(
    *,
    run_summary: dict[str, Any],
    conclusion: str,
    summary_text: str,
    sandbox_by: str,
    environment: str,
    sandbox_ref: str,
    checks: list[dict[str, str]],
    copied_logs: list[dict[str, str]],
    copied_artifacts: list[dict[str, str]],
) -> dict[str, Any]:
    """Строит sandbox-result.json."""
    return {
        "version": 1,
        "run_id": run_summary["run_id"],
        "sandboxed_at_utc": datetime.now(timezone.utc).isoformat(),
        "sandboxed_by": sandbox_by,
        "environment": environment,
        "sandbox_ref": sandbox_ref,
        "conclusion": conclusion,
        "summary": summary_text,
        "checks": checks,
        "check_summary": summarize_checks(checks),
        "logs": copied_logs,
        "artifacts": copied_artifacts,
    }


def update_execution_state(
    execution_state: dict[str, Any] | None,
    *,
    status: str,
    next_action: str,
    sandbox_result: dict[str, Any],
) -> dict[str, Any] | None:
    """Обновляет execution-state.json, если он существует."""
    if execution_state is None:
        return None

    updated = clone_json_compatible(execution_state)
    updated["phase"] = "sandbox_recorded"
    updated["status"] = status
    updated["next_action"] = next_action
    updated["sandboxed_at_utc"] = sandbox_result["sandboxed_at_utc"]
    updated["sandbox"] = {
        "sandboxed_by": sandbox_result["sandboxed_by"],
        "environment": sandbox_result["environment"],
        "sandbox_ref": sandbox_result["sandbox_ref"],
        "conclusion": sandbox_result["conclusion"],
        "summary": sandbox_result["summary"],
        "check_summary": sandbox_result["check_summary"],
        "log_count": len(sandbox_result["logs"]),
        "artifact_count": len(sandbox_result["artifacts"]),
    }
    return updated


def build_output(
    run_dir: Path,
    *,
    conclusion: str,
    summary_text: str,
    sandbox_by: str,
    environment: str,
    sandbox_ref: str,
    checks: list[dict[str, str]],
    log_paths: list[Path],
    artifact_paths: list[Path],
) -> dict[str, Any]:
    """Фиксирует sandbox-stage и обновляет run bundle."""
    summary_path = run_dir / "run-summary.json"
    plan_path = run_dir / "plan.json"
    execution_state_path = run_dir / "execution-state.json"
    sandbox_result_path = run_dir / "sandbox-result.json"

    if not summary_path.is_file():
        raise FileNotFoundError(f"Не найден файл: {summary_path}")
    if not plan_path.is_file():
        raise FileNotFoundError(f"Не найден файл: {plan_path}")

    run_summary = load_json(summary_path)
    plan_payload = load_json(plan_path)
    execution_state = load_json(execution_state_path) if execution_state_path.is_file() else None

    ensure_sandbox_allowed(run_summary, plan_payload)
    copied_logs = copy_files_to_run_dir(
        run_dir,
        source_paths=log_paths,
        target_dir_name="sandbox-logs",
    )
    copied_artifacts = copy_files_to_run_dir(
        run_dir,
        source_paths=artifact_paths,
        target_dir_name="sandbox-artifacts",
    )

    sandbox_result = build_sandbox_result(
        run_summary=run_summary,
        conclusion=conclusion,
        summary_text=summary_text,
        sandbox_by=sandbox_by,
        environment=environment,
        sandbox_ref=sandbox_ref,
        checks=checks,
        copied_logs=copied_logs,
        copied_artifacts=copied_artifacts,
    )

    updated_plan = update_plan_for_sandbox(plan_payload, conclusion)
    status, next_action = derive_status_and_next_action(updated_plan, conclusion)
    updated_execution_state = update_execution_state(
        execution_state,
        status=status,
        next_action=next_action,
        sandbox_result=sandbox_result,
    )

    artifacts = run_summary.setdefault("artifacts", {})
    artifacts["sandbox_result"] = str(sandbox_result_path.relative_to(ROOT)).replace("\\", "/")

    run_summary["status"] = status
    run_summary["next_action"] = next_action
    run_summary["artifacts"] = artifacts
    run_summary["sandbox"] = {
        "sandboxed_by": sandbox_by,
        "environment": environment,
        "sandbox_ref": sandbox_ref,
        "conclusion": conclusion,
        "summary": summary_text,
        "check_summary": sandbox_result["check_summary"],
        "log_count": len(copied_logs),
        "artifact_count": len(copied_artifacts),
    }

    write_json(sandbox_result_path, sandbox_result)
    write_json(plan_path, updated_plan)
    if updated_execution_state is not None:
        write_json(execution_state_path, updated_execution_state)
    write_json(summary_path, run_summary)

    return {
        "run_id": run_summary["run_id"],
        "run_dir": str(run_dir.relative_to(ROOT)).replace("\\", "/"),
        "status": status,
        "next_action": next_action,
        "conclusion": conclusion,
        "check_summary": sandbox_result["check_summary"],
        "log_count": len(copied_logs),
        "artifact_count": len(copied_artifacts),
        "artifacts": {
            "sandbox_result": artifacts["sandbox_result"],
        },
    }


def parse_args() -> argparse.Namespace:
    """Парсит аргументы CLI."""
    parser = argparse.ArgumentParser(
        description="Фиксация sandbox-stage и запись sandbox artifacts в run bundle.",
    )
    parser.add_argument("--run-dir", help="Путь к директории run bundle.")
    parser.add_argument("--run-id", help="Идентификатор запуска внутри runs-dir.")
    parser.add_argument(
        "--runs-dir",
        default=str(DEFAULT_RUNS_DIR.relative_to(ROOT)).replace("\\", "/"),
        help="Базовая директория запусков (по умолчанию: runs).",
    )
    parser.add_argument(
        "--conclusion",
        required=True,
        choices=sorted(VALID_CONCLUSIONS),
        help="Итог sandbox-stage: passed, failed, partial, blocked или skipped.",
    )
    parser.add_argument(
        "--check-result",
        action="append",
        help="Результат sandbox-check в формате check-id=status или check-id=status|note.",
    )
    parser.add_argument("--checks-file", help="JSON-файл со списком sandbox checks.")
    parser.add_argument("--summary", default="", help="Короткое описание результатов sandbox-stage.")
    parser.add_argument("--summary-file", help="Путь к файлу с описанием sandbox-stage.")
    parser.add_argument("--sandbox-by", default="sandbox_runner", help="Кто зафиксировал sandbox-stage.")
    parser.add_argument("--environment", default="isolated", help="Имя изолированной среды.")
    parser.add_argument("--sandbox-ref", default="", help="Внешний идентификатор sandbox job/run.")
    parser.add_argument(
        "--log-file",
        action="append",
        help="Путь к log file, который нужно скопировать в run bundle.",
    )
    parser.add_argument("--logs-file", help="Путь к файлу со списком log files, по одному на строку.")
    parser.add_argument(
        "--artifact-file",
        action="append",
        help="Путь к артефакту sandbox-stage, который нужно скопировать в run bundle.",
    )
    parser.add_argument("--artifacts-file", help="Путь к файлу со списком sandbox artifacts, по одному на строку.")
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
            conclusion=args.conclusion,
            summary_text=read_summary(args),
            sandbox_by=args.sandbox_by.strip() or "sandbox_runner",
            environment=args.environment.strip() or "isolated",
            sandbox_ref=args.sandbox_ref.strip(),
            checks=read_checks(args),
            log_paths=read_path_list(args.log_file, args.logs_file),
            artifact_paths=read_path_list(args.artifact_file, args.artifacts_file),
        )
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        json.dump(
            {
                "error": str(exc),
                "conclusion": args.conclusion,
            },
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
