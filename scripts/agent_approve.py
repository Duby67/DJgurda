#!/usr/bin/env python3
"""Обновление approval checkpoints внутри run bundle."""

from __future__ import annotations

import argparse
import json
import sys

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_execute import DEFAULT_RUNS_DIR
from agent_route import ROOT


RUN_CHECKS_ID = "run_checks"
COMMIT_ID = "commit"
PUSH_ID = "push"
VALID_ACTIONS = {"approve", "reject", "reset"}


def load_json(path: Path) -> dict[str, Any]:
    """Читает JSON-файл."""
    return json.loads(path.read_text(encoding="utf-8"))


def clone_json_compatible(payload: Any) -> Any:
    """Делает безопасную глубокую копию JSON-совместимого объекта."""
    return json.loads(json.dumps(payload, ensure_ascii=False))


def write_json(path: Path, payload: Any) -> None:
    """Записывает JSON-файл."""
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


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


def find_checkpoint(approval_payload: dict[str, Any], checkpoint_id: str) -> dict[str, Any]:
    """Находит checkpoint по id."""
    for checkpoint in approval_payload.get("checkpoints", []):
        if checkpoint.get("id") == checkpoint_id:
            return checkpoint
    raise KeyError(f"Checkpoint '{checkpoint_id}' не найден")


def apply_action_to_checkpoint(checkpoint: dict[str, Any], action: str) -> None:
    """Применяет действие к checkpoint."""
    if not checkpoint.get("required", True) and action != "reset":
        raise ValueError(f"Checkpoint '{checkpoint['id']}' не требует approval")

    if action == "approve":
        checkpoint["status"] = "approved"
    elif action == "reject":
        checkpoint["status"] = "rejected"
    elif action == "reset":
        checkpoint["status"] = "awaiting_approval" if checkpoint.get("required", True) else "not_required"
    else:
        raise ValueError(f"Неподдерживаемое действие: {action}")


def load_optional_json(path: Path) -> dict[str, Any] | None:
    """Читает optional JSON-файл."""
    if not path.is_file():
        return None
    return load_json(path)


def append_history(history: list[dict[str, Any]], *, checkpoint_id: str, action: str, note: str) -> None:
    """Добавляет запись в approval history."""
    history.append(
        {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "checkpoint_id": checkpoint_id,
            "action": action,
            "note": note,
        }
    )


def checkpoint_status_map(approval_payload: dict[str, Any]) -> dict[str, str]:
    """Возвращает map checkpoint_id -> status."""
    return {
        checkpoint["id"]: checkpoint["status"]
        for checkpoint in approval_payload.get("checkpoints", [])
    }


def validate_action_transition(
    approval_payload: dict[str, Any],
    execution_state: dict[str, Any] | None,
    *,
    checkpoint_id: str,
    action: str,
) -> None:
    """Проверяет, что approval transition допустим для текущего lifecycle."""
    if action != "approve":
        return

    statuses = checkpoint_status_map(approval_payload)
    current_phase = (execution_state or {}).get("phase", "")

    if checkpoint_id == PUSH_ID and statuses.get(COMMIT_ID) != "approved":
        raise ValueError("Нельзя approve checkpoint 'push' до approval checkpoint 'commit'")

    if checkpoint_id in {COMMIT_ID, PUSH_ID} and current_phase == "context_loaded":
        raise ValueError(
            f"Нельзя approve checkpoint '{checkpoint_id}' до завершения implementation/verification lifecycle",
        )


def derive_status_and_next_action(
    approval_payload: dict[str, Any],
    execution_state: dict[str, Any] | None,
) -> tuple[str, str]:
    """Вычисляет новый статус и следующий шаг run bundle."""
    statuses = checkpoint_status_map(approval_payload)
    run_checks_status = statuses.get(RUN_CHECKS_ID, "awaiting_approval")
    commit_status = statuses.get(COMMIT_ID, "awaiting_approval")
    push_status = statuses.get(PUSH_ID, "awaiting_approval")
    current_phase = (execution_state or {}).get("phase")

    if "rejected" in statuses.values():
        return "approval_rejected", "review_rejection_or_replan"

    if current_phase == "context_loaded":
        if run_checks_status == "approved":
            return "approved_for_implementation", "implement_change"
        if run_checks_status == "awaiting_approval":
            return "context_loaded_awaiting_manual_review", "review_escalation_and_approve_implementation"
        return "context_loaded", "review_context_state"

    if commit_status == "approved" and push_status == "approved":
        return "fully_approved", "ready_for_push_execution"
    if commit_status == "approved":
        return "approved_for_push_decision", "decide_on_push"
    if commit_status == "awaiting_approval":
        return "awaiting_commit_approval", "request_commit_approval"
    return "planned", "continue_run"


def update_plan_steps(plan_payload: dict[str, Any], approval_payload: dict[str, Any]) -> dict[str, Any]:
    """Обновляет plan.json на основе approval состояния."""
    updated = clone_json_compatible(plan_payload)
    statuses = checkpoint_status_map(approval_payload)
    run_checks_status = statuses.get(RUN_CHECKS_ID, "awaiting_approval")
    all_approved = all(status in {"approved", "not_required"} for status in statuses.values())

    for step in updated.get("plan", []):
        if step.get("id") == "manual_review":
            step["status"] = "completed" if run_checks_status in {"approved", "rejected"} else "pending"
        elif step.get("id") == "request_approval":
            step["status"] = "completed" if all_approved else "pending"
    return updated


def update_execution_state(execution_state: dict[str, Any] | None, approval_payload: dict[str, Any], *, status: str, next_action: str) -> dict[str, Any] | None:
    """Обновляет execution-state.json, если он существует."""
    if execution_state is None:
        return None

    updated = clone_json_compatible(execution_state)
    updated["status"] = status
    updated["next_action"] = next_action
    updated["approval"] = {
        "needs_manual_review": approval_payload.get("needs_manual_review", False),
        "escalation_reasons": approval_payload.get("escalation_reasons", []),
        "checkpoint_statuses": checkpoint_status_map(approval_payload),
    }
    return updated


def build_output(run_dir: Path, checkpoint_id: str, action: str, note: str) -> dict[str, Any]:
    """Применяет approval action и обновляет run bundle."""
    approval_path = run_dir / "approval-checkpoints.json"
    summary_path = run_dir / "run-summary.json"
    plan_path = run_dir / "plan.json"
    history_path = run_dir / "approval-history.json"
    execution_state_path = run_dir / "execution-state.json"

    if not approval_path.is_file():
        raise FileNotFoundError(f"Не найден файл: {approval_path}")
    if not summary_path.is_file():
        raise FileNotFoundError(f"Не найден файл: {summary_path}")
    if not plan_path.is_file():
        raise FileNotFoundError(f"Не найден файл: {plan_path}")

    approval_payload = load_json(approval_path)
    run_summary = load_json(summary_path)
    plan_payload = load_json(plan_path)
    execution_state = load_optional_json(execution_state_path)
    history_payload = load_optional_json(history_path)
    history_entries = history_payload.get("entries", []) if history_payload else []

    checkpoint = find_checkpoint(approval_payload, checkpoint_id)
    previous_status = checkpoint["status"]
    validate_action_transition(
        approval_payload,
        execution_state,
        checkpoint_id=checkpoint_id,
        action=action,
    )
    apply_action_to_checkpoint(checkpoint, action)
    append_history(history_entries, checkpoint_id=checkpoint_id, action=action, note=note)

    status, next_action = derive_status_and_next_action(approval_payload, execution_state)
    updated_plan = update_plan_steps(plan_payload, approval_payload)
    updated_execution_state = update_execution_state(
        execution_state,
        approval_payload,
        status=status,
        next_action=next_action,
    )

    run_summary["status"] = status
    run_summary["next_action"] = next_action
    run_summary["approval"] = approval_payload
    artifacts = run_summary.setdefault("artifacts", {})
    artifacts["approval"] = str(approval_path.relative_to(ROOT)).replace("\\", "/")
    artifacts["approval_history"] = str(history_path.relative_to(ROOT)).replace("\\", "/")

    write_json(approval_path, approval_payload)
    write_json(plan_path, updated_plan)
    write_json(
        history_path,
        {
            "version": 1,
            "run_id": run_summary["run_id"],
            "entries": history_entries,
        },
    )
    if updated_execution_state is not None:
        write_json(execution_state_path, updated_execution_state)
    write_json(summary_path, run_summary)

    return {
        "run_id": run_summary["run_id"],
        "run_dir": str(run_dir.relative_to(ROOT)).replace("\\", "/"),
        "updated_checkpoint": {
            "id": checkpoint_id,
            "previous_status": previous_status,
            "new_status": checkpoint["status"],
            "action": action,
            "note": note,
        },
        "status": status,
        "next_action": next_action,
        "approval": {
            "needs_manual_review": approval_payload.get("needs_manual_review", False),
            "escalation_reasons": approval_payload.get("escalation_reasons", []),
            "checkpoint_statuses": checkpoint_status_map(approval_payload),
        },
        "history_length": len(history_entries),
    }


def parse_args() -> argparse.Namespace:
    """Парсит аргументы CLI."""
    parser = argparse.ArgumentParser(
        description="Обновление approval checkpoint внутри run bundle.",
    )
    parser.add_argument("--run-dir", help="Путь к директории run bundle.")
    parser.add_argument("--run-id", help="Идентификатор запуска внутри runs-dir.")
    parser.add_argument(
        "--runs-dir",
        default=str(DEFAULT_RUNS_DIR.relative_to(ROOT)).replace("\\", "/"),
        help="Базовая директория запусков (по умолчанию: local/runs).",
    )
    parser.add_argument(
        "--checkpoint",
        required=True,
        choices=[RUN_CHECKS_ID, COMMIT_ID, PUSH_ID],
        help="Идентификатор approval checkpoint.",
    )
    parser.add_argument(
        "--action",
        required=True,
        choices=sorted(VALID_ACTIONS),
        help="Действие над checkpoint: approve, reject или reset.",
    )
    parser.add_argument(
        "--note",
        default="",
        help="Необязательная заметка для approval history.",
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
        result = build_output(run_dir, checkpoint_id=args.checkpoint, action=args.action, note=args.note)
    except (FileNotFoundError, KeyError, ValueError) as exc:
        json.dump(
            {
                "error": str(exc),
                "checkpoint": args.checkpoint,
                "action": args.action,
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
