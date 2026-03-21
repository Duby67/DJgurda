#!/usr/bin/env python3
"""Показывает компактный статус run bundle и его артефактов."""

from __future__ import annotations

import argparse
import json
import sys

from pathlib import Path
from typing import Any

from agent_execute import DEFAULT_RUNS_DIR
from agent_route import ROOT


def load_json(path: Path) -> dict[str, Any]:
    """Читает JSON-файл."""
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_rel_path(value: str) -> str:
    """Нормализует относительный путь."""
    return value.strip().replace("\\", "/").lstrip("./")


def resolve_run_dir(args: argparse.Namespace) -> Path:
    """Определяет директорию запуска по аргументам."""
    if args.run_dir and args.run_id:
        raise ValueError("Нельзя одновременно использовать --run-dir и --run-id")
    if args.run_dir:
        return ROOT / normalize_rel_path(args.run_dir)
    if args.run_id:
        return (ROOT / normalize_rel_path(args.runs_dir)) / args.run_id.strip()
    raise ValueError("Нужно указать либо --run-dir, либо --run-id")


def collect_artifact_status(artifacts: dict[str, str]) -> dict[str, Any]:
    """Проверяет наличие артефактов на диске."""
    available: dict[str, str] = {}
    missing: dict[str, str] = {}

    for key, rel_path in artifacts.items():
        full_path = ROOT / normalize_rel_path(rel_path)
        if full_path.exists():
            available[key] = rel_path
        else:
            missing[key] = rel_path

    return {
        "total": len(artifacts),
        "available_count": len(available),
        "missing_count": len(missing),
        "available": available,
        "missing": missing,
    }


def summarize_plan(plan_payload: dict[str, Any]) -> dict[str, Any]:
    """Считает прогресс по шагам плана."""
    steps = plan_payload.get("plan", [])
    by_status: dict[str, int] = {}
    next_pending: dict[str, Any] | None = None

    for step in steps:
        status = step.get("status", "unknown")
        by_status[status] = by_status.get(status, 0) + 1
        if next_pending is None and status != "completed":
            next_pending = {
                "id": step.get("id"),
                "title": step.get("title"),
                "owner": step.get("owner"),
                "status": status,
            }

    return {
        "total_steps": len(steps),
        "by_status": by_status,
        "next_pending_step": next_pending,
    }


def summarize_approval(approval_payload: dict[str, Any]) -> dict[str, Any]:
    """Считает сводку по approval checkpoints."""
    checkpoints = approval_payload.get("checkpoints", [])
    awaiting = [item["id"] for item in checkpoints if item.get("status") == "awaiting_approval"]
    approved = [item["id"] for item in checkpoints if item.get("status") == "approved"]
    rejected = [item["id"] for item in checkpoints if item.get("status") == "rejected"]
    skipped = [item["id"] for item in checkpoints if item.get("status") == "not_required"]

    return {
        "needs_manual_review": approval_payload.get("needs_manual_review", False),
        "escalation_reasons": approval_payload.get("escalation_reasons", []),
        "awaiting_approval": awaiting,
        "approved": approved,
        "rejected": rejected,
        "not_required": skipped,
        "checkpoint_statuses": {
            item["id"]: item.get("status", "unknown")
            for item in checkpoints
        },
        "checkpoint_details": checkpoints,
    }


def load_optional_json(path: Path) -> dict[str, Any] | None:
    """Читает optional JSON-файл, если он существует."""
    if not path.is_file():
        return None
    return load_json(path)


def summarize_approval_history(history_payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """Сводит approval history к компактному формату."""
    if history_payload is None:
        return None

    entries = history_payload.get("entries", [])
    latest_entry = entries[-1] if entries else None

    by_action: dict[str, int] = {}
    by_checkpoint: dict[str, int] = {}
    for entry in entries:
        action = entry.get("action", "unknown")
        checkpoint_id = entry.get("checkpoint_id", "unknown")
        by_action[action] = by_action.get(action, 0) + 1
        by_checkpoint[checkpoint_id] = by_checkpoint.get(checkpoint_id, 0) + 1

    return {
        "total_events": len(entries),
        "by_action": by_action,
        "by_checkpoint": by_checkpoint,
        "latest_event": latest_entry,
    }


def summarize_verification(verification_payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """Сводит verification result к компактному формату."""
    if verification_payload is None:
        return None

    checks = verification_payload.get("checks", [])
    failed_checks = [item.get("id") for item in checks if item.get("status") == "failed"]
    blocked_checks = [item.get("id") for item in checks if item.get("status") == "blocked"]

    return {
        "verified_at_utc": verification_payload.get("verified_at_utc"),
        "verified_by": verification_payload.get("verified_by"),
        "conclusion": verification_payload.get("conclusion"),
        "summary": verification_payload.get("summary", ""),
        "check_summary": verification_payload.get("check_summary", {}),
        "failed_checks": failed_checks,
        "blocked_checks": blocked_checks,
        "log_count": len(verification_payload.get("logs", [])),
    }


def summarize_sandbox(sandbox_payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """Сводит sandbox result к компактному формату."""
    if sandbox_payload is None:
        return None

    checks = sandbox_payload.get("checks", [])
    failed_checks = [item.get("id") for item in checks if item.get("status") == "failed"]
    blocked_checks = [item.get("id") for item in checks if item.get("status") == "blocked"]

    return {
        "sandboxed_at_utc": sandbox_payload.get("sandboxed_at_utc"),
        "sandboxed_by": sandbox_payload.get("sandboxed_by"),
        "environment": sandbox_payload.get("environment"),
        "sandbox_ref": sandbox_payload.get("sandbox_ref", ""),
        "conclusion": sandbox_payload.get("conclusion"),
        "summary": sandbox_payload.get("summary", ""),
        "check_summary": sandbox_payload.get("check_summary", {}),
        "failed_checks": failed_checks,
        "blocked_checks": blocked_checks,
        "log_count": len(sandbox_payload.get("logs", [])),
        "artifact_count": len(sandbox_payload.get("artifacts", [])),
    }


def build_blockers(
    *,
    run_summary: dict[str, Any],
    artifact_status: dict[str, Any],
    approval_summary: dict[str, Any],
    plan_summary: dict[str, Any],
) -> list[str]:
    """Строит список текущих blockers для lifecycle run bundle."""
    blockers: list[str] = []

    if artifact_status["missing"]:
        blockers.append("missing_artifacts")
    if approval_summary["rejected"]:
        blockers.append("approval_rejected")
    if approval_summary["needs_manual_review"] and "run_checks" in approval_summary["awaiting_approval"]:
        blockers.append("manual_review_not_approved")
    if run_summary.get("status") == "awaiting_manual_review":
        blockers.append("context_not_loaded")
    if run_summary.get("status") == "verification_failed":
        blockers.append("verification_failed")
    if run_summary.get("status") == "verification_blocked":
        blockers.append("verification_blocked")
    if run_summary.get("status") == "sandbox_failed":
        blockers.append("sandbox_failed")
    if run_summary.get("status") == "sandbox_blocked":
        blockers.append("sandbox_blocked")
    if plan_summary.get("next_pending_step") is None and not approval_summary["rejected"]:
        blockers.append("plan_has_no_pending_steps")

    return blockers


def build_readiness(
    *,
    run_summary: dict[str, Any],
    approval_summary: dict[str, Any],
) -> dict[str, bool]:
    """Показывает, какие действия уже можно выполнять по текущему статусу."""
    checkpoint_statuses = approval_summary.get("checkpoint_statuses", {})
    run_checks_status = checkpoint_statuses.get("run_checks")
    commit_status = checkpoint_statuses.get("commit")
    push_status = checkpoint_statuses.get("push")

    return {
        "can_implement": run_summary.get("next_action") == "implement_change",
        "can_request_commit_approval": run_checks_status in {"approved", "not_required"},
        "can_request_push_approval": commit_status == "approved",
        "can_push": push_status == "approved",
    }


def build_status(run_dir: Path) -> dict[str, Any]:
    """Собирает итоговый статус run bundle."""
    summary_path = run_dir / "run-summary.json"
    plan_path = run_dir / "plan.json"
    approval_path = run_dir / "approval-checkpoints.json"
    execution_state_path = run_dir / "execution-state.json"
    approval_history_path = run_dir / "approval-history.json"
    verification_result_path = run_dir / "verification-result.json"
    sandbox_result_path = run_dir / "sandbox-result.json"

    if not summary_path.is_file():
        raise FileNotFoundError(f"Не найден файл: {summary_path}")
    if not plan_path.is_file():
        raise FileNotFoundError(f"Не найден файл: {plan_path}")
    if not approval_path.is_file():
        raise FileNotFoundError(f"Не найден файл: {approval_path}")

    run_summary = load_json(summary_path)
    plan_payload = load_json(plan_path)
    approval_payload = load_json(approval_path)
    execution_state = load_optional_json(execution_state_path)
    approval_history = load_optional_json(approval_history_path)
    verification_payload = load_optional_json(verification_result_path)
    sandbox_payload = load_optional_json(sandbox_result_path)

    artifact_status = collect_artifact_status(run_summary.get("artifacts", {}))
    plan_summary = summarize_plan(plan_payload)
    approval_summary = summarize_approval(approval_payload)
    approval_history_summary = summarize_approval_history(approval_history)
    verification_summary = summarize_verification(verification_payload)
    sandbox_summary = summarize_sandbox(sandbox_payload)
    blockers = build_blockers(
        run_summary=run_summary,
        artifact_status=artifact_status,
        approval_summary=approval_summary,
        plan_summary=plan_summary,
    )
    readiness = build_readiness(
        run_summary=run_summary,
        approval_summary=approval_summary,
    )

    output: dict[str, Any] = {
        "run_id": run_summary["run_id"],
        "run_dir": str(run_dir.relative_to(ROOT)).replace("\\", "/"),
        "task_type": run_summary["task_type"],
        "status": run_summary["status"],
        "next_action": run_summary["next_action"],
        "recommended_agents": run_summary.get("recommended_agents", []),
        "changed_paths": run_summary.get("changed_paths", []),
        "artifacts": artifact_status,
        "plan": plan_summary,
        "approval": approval_summary,
        "readiness": readiness,
        "blockers": blockers,
    }

    if execution_state is not None:
        output["execution_state"] = {
            "phase": execution_state.get("phase"),
            "status": execution_state.get("status"),
            "next_action": execution_state.get("next_action"),
            "loaded_at_utc": execution_state.get("loaded_at_utc"),
            "summary": execution_state.get("summary", {}),
        }
    if approval_history_summary is not None:
        output["approval_history"] = approval_history_summary
    if verification_summary is not None:
        output["verification"] = verification_summary
    if sandbox_summary is not None:
        output["sandbox"] = sandbox_summary

    return output


def parse_args() -> argparse.Namespace:
    """Парсит аргументы CLI."""
    parser = argparse.ArgumentParser(
        description="Показ компактного статуса run bundle.",
    )
    parser.add_argument("--run-dir", help="Путь к директории run bundle.")
    parser.add_argument("--run-id", help="Идентификатор запуска внутри runs-dir.")
    parser.add_argument(
        "--runs-dir",
        default=str(DEFAULT_RUNS_DIR.relative_to(ROOT)).replace("\\", "/"),
        help="Базовая директория запусков (по умолчанию: local/runs).",
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
        result = build_status(run_dir)
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
