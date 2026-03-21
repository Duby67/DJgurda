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
    skipped = [item["id"] for item in checkpoints if item.get("status") == "not_required"]

    return {
        "needs_manual_review": approval_payload.get("needs_manual_review", False),
        "escalation_reasons": approval_payload.get("escalation_reasons", []),
        "awaiting_approval": awaiting,
        "approved": approved,
        "not_required": skipped,
    }


def load_optional_json(path: Path) -> dict[str, Any] | None:
    """Читает optional JSON-файл, если он существует."""
    if not path.is_file():
        return None
    return load_json(path)


def build_status(run_dir: Path) -> dict[str, Any]:
    """Собирает итоговый статус run bundle."""
    summary_path = run_dir / "run-summary.json"
    plan_path = run_dir / "plan.json"
    approval_path = run_dir / "approval-checkpoints.json"
    execution_state_path = run_dir / "execution-state.json"

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

    artifact_status = collect_artifact_status(run_summary.get("artifacts", {}))
    plan_summary = summarize_plan(plan_payload)
    approval_summary = summarize_approval(approval_payload)

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
    }

    if execution_state is not None:
        output["execution_state"] = {
            "phase": execution_state.get("phase"),
            "status": execution_state.get("status"),
            "loaded_at_utc": execution_state.get("loaded_at_utc"),
            "summary": execution_state.get("summary", {}),
        }

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
    run_dir = resolve_run_dir(args)
    result = build_status(run_dir)

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
