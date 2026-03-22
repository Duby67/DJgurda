#!/usr/bin/env python3
"""Показывает компактный статус run bundle и его артефактов."""

from __future__ import annotations

import argparse
import json
import sys

from pathlib import Path
from typing import Any

from .approve import RUN_CHECKS_ID, COMMIT_ID, PUSH_ID
from .apply import collect_git_snapshot, ensure_apply_allowed, resolve_applied_files
from .close import VALID_OUTCOMES, ensure_close_allowed
from .commit import ensure_commit_allowed
from .execute import DEFAULT_RUNS_DIR
from .push import ensure_push_allowed
from .request_approval import ensure_request_allowed, read_requested_checkpoints
from scripts.config import ROOT


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


def summarize_review(review_payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """Сводит review result к компактному формату."""
    if review_payload is None:
        return None

    return {
        "reviewed_at_utc": review_payload.get("reviewed_at_utc"),
        "reviewed_by": review_payload.get("reviewed_by"),
        "conclusion": review_payload.get("conclusion"),
        "summary": review_payload.get("summary", ""),
        "finding_count": review_payload.get("finding_count", 0),
        "risk_count": review_payload.get("risk_count", 0),
        "findings": review_payload.get("findings", []),
        "residual_risks": review_payload.get("residual_risks", []),
    }


def summarize_approval_request(approval_request_payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """Сводит approval request packet к компактному формату."""
    if approval_request_payload is None:
        return None

    return {
        "requested_at_utc": approval_request_payload.get("requested_at_utc"),
        "requested_by": approval_request_payload.get("requested_by"),
        "summary": approval_request_payload.get("summary", ""),
        "requested_checkpoints": approval_request_payload.get("requested_checkpoints", []),
    }


def summarize_commit(commit_payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """Сводит commit result к компактному формату."""
    if commit_payload is None:
        return None

    return {
        "recorded_at_utc": commit_payload.get("recorded_at_utc"),
        "committed_by": commit_payload.get("committed_by"),
        "mode": commit_payload.get("mode"),
        "message": commit_payload.get("message", ""),
        "files": commit_payload.get("files", []),
        "commit_created": commit_payload.get("commit_created", False),
        "commit_hash": commit_payload.get("commit_hash"),
        "diff_summary": commit_payload.get("git", {}).get("diff_summary", {}),
        "warnings": commit_payload.get("git", {}).get("warnings", []),
    }


def summarize_push_execution(push_payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """Сводит push result к компактному формату."""
    if push_payload is None:
        return None

    return {
        "recorded_at_utc": push_payload.get("recorded_at_utc"),
        "pushed_by": push_payload.get("pushed_by"),
        "mode": push_payload.get("mode"),
        "remote": push_payload.get("remote"),
        "branch": push_payload.get("branch"),
        "push_created": push_payload.get("push_created", False),
        "push_stdout": push_payload.get("git_push_stdout", ""),
        "warnings": push_payload.get("warnings", []),
    }


def summarize_closure(close_payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """Сводит close result к компактному формату."""
    if close_payload is None:
        return None

    final_state = close_payload.get("final_state", {})
    return {
        "closed_at_utc": close_payload.get("closed_at_utc"),
        "closed_by": close_payload.get("closed_by"),
        "outcome": close_payload.get("outcome"),
        "summary": close_payload.get("summary", ""),
        "note_count": len(close_payload.get("notes", [])),
        "status_before_close": close_payload.get("status_before_close"),
        "next_action_before_close": close_payload.get("next_action_before_close"),
        "commit_created": final_state.get("commit_created", False),
        "push_created": final_state.get("push_created", False),
    }


def step_exists(plan_payload: dict[str, Any], step_id: str) -> bool:
    """Проверяет наличие шага в plan.json."""
    return any(step.get("id") == step_id for step in plan_payload.get("plan", []))


def is_run_checks_approval_allowed(approval_payload: dict[str, Any]) -> bool:
    """Показывает, можно ли сейчас approve checkpoint run_checks."""
    checkpoints = {
        item["id"]: item
        for item in approval_payload.get("checkpoints", [])
    }
    checkpoint = checkpoints.get(RUN_CHECKS_ID)
    if checkpoint is None:
        return False
    if not checkpoint.get("required", True):
        return False
    return checkpoint.get("status") != "approved"


def is_request_allowed(
    *,
    run_summary: dict[str, Any],
    plan_payload: dict[str, Any],
    approval_payload: dict[str, Any],
    requested_checkpoints: list[str],
) -> bool:
    """Проверяет, можно ли сейчас собрать approval request для указанных checkpoints."""
    if not requested_checkpoints:
        return False
    try:
        ensure_request_allowed(run_summary, plan_payload, approval_payload, requested_checkpoints)
    except ValueError:
        return False
    return True


def auto_requested_checkpoints(approval_payload: dict[str, Any]) -> list[str]:
    """Определяет checkpoints для approval request в default-режиме."""
    try:
        return read_requested_checkpoints(argparse.Namespace(checkpoint=None), approval_payload)
    except ValueError:
        return []


def explain_run_checks_approval(approval_payload: dict[str, Any]) -> list[str]:
    """Объясняет, почему run_checks approval доступен или недоступен."""
    checkpoints = {
        item["id"]: item
        for item in approval_payload.get("checkpoints", [])
    }
    checkpoint = checkpoints.get(RUN_CHECKS_ID)
    if checkpoint is None:
        return ["run_checks_checkpoint_missing"]
    if not checkpoint.get("required", True):
        return ["run_checks_not_required"]

    status = checkpoint.get("status", "unknown")
    if status == "approved":
        return ["run_checks_already_approved"]
    if status == "rejected":
        return ["run_checks_rejected"]
    if status == "awaiting_approval":
        return []
    return [f"run_checks_status_{status}"]


def can_create_commit(run_summary: dict[str, Any], approval_payload: dict[str, Any]) -> bool:
    """Показывает, можно ли сейчас запускать commit-stage."""
    try:
        ensure_commit_allowed(run_summary, approval_payload)
    except ValueError:
        return False
    return True


def can_execute_push(run_summary: dict[str, Any], approval_payload: dict[str, Any]) -> bool:
    """Показывает, можно ли сейчас запускать push-stage."""
    try:
        ensure_push_allowed(run_summary, approval_payload)
    except ValueError:
        return False
    return True


def closable_outcomes(run_summary: dict[str, Any]) -> list[str]:
    """Возвращает список outcome, допустимых для lifecycle close-stage."""
    allowed: list[str] = []
    for outcome in sorted(VALID_OUTCOMES):
        try:
            ensure_close_allowed(run_summary, outcome)
        except ValueError:
            continue
        allowed.append(outcome)
    return allowed


def explain_request_approval(
    *,
    run_summary: dict[str, Any],
    plan_payload: dict[str, Any],
    approval_payload: dict[str, Any],
    requested_checkpoints: list[str],
) -> list[str]:
    """Объясняет, почему approval request доступен или недоступен."""
    if not requested_checkpoints:
        return ["no_requestable_checkpoints"]
    if not step_exists(plan_payload, "request_approval"):
        return ["request_approval_step_missing"]

    statuses = approval_summary_from_payload(approval_payload)["checkpoint_statuses"]
    blockers: list[str] = []

    allowed_statuses = {
        "review_passed_pending_approval",
        "review_partial_pending_approval",
        "awaiting_commit_approval",
        "approved_for_push_decision",
        "awaiting_push_approval",
    }
    allowed_next_actions = {
        "request_approval",
        "request_commit_approval",
        "decide_on_push",
        "request_push_approval",
        "await_commit_approval",
        "await_push_approval",
    }
    if (
        run_summary.get("status") not in allowed_statuses
        and run_summary.get("next_action") not in allowed_next_actions
    ):
        blockers.append("review_not_completed_for_approval_request")

    if PUSH_ID in requested_checkpoints:
        if statuses.get(COMMIT_ID) != "approved":
            blockers.append("push_requires_commit_approval")
        commit_result_rel = run_summary.get("artifacts", {}).get("commit_result", "")
        if not commit_result_rel:
            blockers.append("push_requires_commit_artifact")
        elif not (ROOT / normalize_rel_path(commit_result_rel)).is_file():
            blockers.append("commit_artifact_missing")
        if not run_summary.get("commit", {}).get("commit_created", False):
            blockers.append("push_requires_real_commit")

    for checkpoint_id in requested_checkpoints:
        status = statuses.get(checkpoint_id, "missing")
        if status not in {"awaiting_approval", "approved"}:
            blockers.append(f"{checkpoint_id}_not_requestable_from_status_{status}")

    try:
        ensure_request_allowed(run_summary, plan_payload, approval_payload, requested_checkpoints)
    except ValueError:
        if not blockers:
            blockers.append("approval_request_not_allowed")
    return blockers


def explain_commit_creation(run_summary: dict[str, Any], approval_payload: dict[str, Any]) -> list[str]:
    """Объясняет, почему commit-stage доступен или недоступен."""
    blockers: list[str] = []
    statuses = approval_summary_from_payload(approval_payload)["checkpoint_statuses"]
    if statuses.get(COMMIT_ID) != "approved":
        blockers.append("commit_approval_missing")

    try:
        ensure_commit_allowed(run_summary, approval_payload)
    except ValueError:
        if not blockers:
            blockers.append("commit_stage_not_ready")
    return blockers


def explain_push_execution(run_summary: dict[str, Any], approval_payload: dict[str, Any]) -> list[str]:
    """Объясняет, почему push-stage доступен или недоступен."""
    blockers: list[str] = []
    statuses = approval_summary_from_payload(approval_payload)["checkpoint_statuses"]
    if statuses.get(PUSH_ID) != "approved":
        blockers.append("push_approval_missing")
    if not run_summary.get("commit", {}).get("commit_created", False):
        blockers.append("push_requires_real_commit")

    try:
        ensure_push_allowed(run_summary, approval_payload)
    except ValueError:
        if not blockers:
            blockers.append("push_stage_not_ready")
    return blockers


def explain_run_close(run_summary: dict[str, Any]) -> list[str]:
    """Объясняет, почему run можно или нельзя закрыть."""
    outcomes = closable_outcomes(run_summary)
    if outcomes:
        return []
    if run_summary.get("status") == "closed":
        return ["run_already_closed"]
    return ["no_supported_close_outcome_for_current_state"]


def approval_summary_from_payload(approval_payload: dict[str, Any]) -> dict[str, Any]:
    """Строит approval summary без повторного чтения файлов."""
    checkpoints = approval_payload.get("checkpoints", [])
    return {
        "needs_manual_review": approval_payload.get("needs_manual_review", False),
        "checkpoint_statuses": {
            item["id"]: item.get("status", "unknown")
            for item in checkpoints
        },
    }


def build_action_blockers(
    *,
    run_summary: dict[str, Any],
    plan_payload: dict[str, Any],
    approval_payload: dict[str, Any],
) -> dict[str, list[str]]:
    """Строит blockers по конкретным lifecycle-действиям."""
    implementation_diff_file_count = implementation_diff_count(run_summary)
    implement_blockers = explain_implement(run_summary, plan_payload, implementation_diff_file_count)

    auto_checkpoints = auto_requested_checkpoints(approval_payload)

    return {
        "approve_run_checks": explain_run_checks_approval(approval_payload),
        "implement": implement_blockers,
        "request_approval": explain_request_approval(
            run_summary=run_summary,
            plan_payload=plan_payload,
            approval_payload=approval_payload,
            requested_checkpoints=auto_checkpoints,
        ),
        "request_commit_approval": explain_request_approval(
            run_summary=run_summary,
            plan_payload=plan_payload,
            approval_payload=approval_payload,
            requested_checkpoints=[COMMIT_ID],
        ),
        "create_commit": explain_commit_creation(run_summary, approval_payload),
        "request_push_approval": explain_request_approval(
            run_summary=run_summary,
            plan_payload=plan_payload,
            approval_payload=approval_payload,
            requested_checkpoints=[PUSH_ID],
        ),
        "push": explain_push_execution(run_summary, approval_payload),
        "close_run": explain_run_close(run_summary),
    }


def explain_implement(
    run_summary: dict[str, Any],
    plan_payload: dict[str, Any],
    implementation_diff_file_count: int | None,
) -> list[str]:
    """Объясняет, почему implement-stage доступен или недоступен."""
    blockers: list[str] = []
    try:
        ensure_apply_allowed(run_summary, plan_payload)
    except ValueError:
        blockers.append("implement_stage_not_ready")
        return blockers

    if implementation_diff_file_count == 0:
        blockers.append("empty_diff_requires_allow_empty_diff")
    elif implementation_diff_file_count is None:
        blockers.append("implementation_diff_unknown")
    return blockers


def build_blockers(
    *,
    run_summary: dict[str, Any],
    artifact_status: dict[str, Any],
    approval_summary: dict[str, Any],
    plan_summary: dict[str, Any],
    action_blockers: dict[str, list[str]],
) -> list[str]:
    """Строит список текущих blockers для lifecycle run bundle."""
    blockers: list[str] = []

    if artifact_status["missing"]:
        blockers.append("missing_artifacts")
    if run_summary.get("status") == "closed":
        return blockers
    if approval_summary["rejected"]:
        blockers.append("approval_rejected")
    if approval_summary["needs_manual_review"] and "run_checks" in approval_summary["awaiting_approval"]:
        blockers.append("manual_review_not_approved")
    if (
        not approval_summary["needs_manual_review"]
        and "run_checks" in approval_summary["awaiting_approval"]
        and run_summary.get("next_action") == "approve_run_checks_before_implementation"
    ):
        blockers.append("run_checks_not_approved")
    if "empty_diff_requires_allow_empty_diff" in action_blockers.get("implement", []):
        blockers.append("empty_diff_requires_allow_empty_diff")
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
    if run_summary.get("status") == "review_failed":
        blockers.append("review_failed")
    if run_summary.get("status") == "review_blocked":
        blockers.append("review_blocked")
    if run_summary.get("status") == "push_failed":
        blockers.append("push_failed")
    if run_summary.get("status") == "push_blocked":
        blockers.append("push_blocked")
    if (
        plan_summary.get("next_pending_step") is None
        and not approval_summary["rejected"]
        and not approval_summary["awaiting_approval"]
        and run_summary.get("next_action") not in {
            "create_commit",
            "execute_push",
            "run_complete",
            "await_commit_approval",
            "await_push_approval",
        }
    ):
        blockers.append("plan_has_no_pending_steps")

    return list(dict.fromkeys(blockers))


def build_readiness(
    *,
    run_summary: dict[str, Any],
    plan_payload: dict[str, Any],
    approval_payload: dict[str, Any],
    approval_summary: dict[str, Any],
) -> dict[str, Any]:
    """Показывает, какие действия уже можно выполнять по текущему статусу."""
    if run_summary.get("status") == "closed":
        return {
            "can_approve_run_checks": False,
            "can_implement": False,
            "can_implement_with_allow_empty_diff": False,
            "implementation_diff_file_count": None,
            "can_request_final_approval": False,
            "can_request_approval": False,
            "requestable_checkpoints": [],
            "can_request_commit_approval": False,
            "can_create_commit": False,
            "can_request_push_approval": False,
            "can_push": False,
            "can_close_run": False,
            "closable_outcomes": [],
        }

    checkpoint_statuses = approval_summary.get("checkpoint_statuses", {})
    run_checks_status = checkpoint_statuses.get("run_checks")
    auto_checkpoints = auto_requested_checkpoints(approval_payload)
    apply_diff_file_count = implementation_diff_count(run_summary)
    can_request_auto = is_request_allowed(
        run_summary=run_summary,
        plan_payload=plan_payload,
        approval_payload=approval_payload,
        requested_checkpoints=auto_checkpoints,
    )
    can_request_commit = is_request_allowed(
        run_summary=run_summary,
        plan_payload=plan_payload,
        approval_payload=approval_payload,
        requested_checkpoints=[COMMIT_ID],
    )
    can_request_push = is_request_allowed(
        run_summary=run_summary,
        plan_payload=plan_payload,
        approval_payload=approval_payload,
        requested_checkpoints=[PUSH_ID],
    )
    can_close_outcomes = closable_outcomes(run_summary)

    return {
        "can_approve_run_checks": is_run_checks_approval_allowed(approval_payload),
        "can_implement": (
            run_checks_status in {"approved", "not_required"}
            and _can_implement(run_summary, plan_payload, allow_empty_diff=False)
        ),
        "can_implement_with_allow_empty_diff": (
            run_checks_status in {"approved", "not_required"}
            and _can_implement(run_summary, plan_payload, allow_empty_diff=True)
        ),
        "implementation_diff_file_count": apply_diff_file_count,
        "can_request_final_approval": can_request_auto,
        "can_request_approval": can_request_auto,
        "requestable_checkpoints": auto_checkpoints if can_request_auto else [],
        "can_request_commit_approval": can_request_commit,
        "can_create_commit": can_create_commit(run_summary, approval_payload),
        "can_request_push_approval": can_request_push,
        "can_push": can_execute_push(run_summary, approval_payload),
        "can_close_run": bool(can_close_outcomes),
        "closable_outcomes": can_close_outcomes,
    }


def implementation_diff_count(run_summary: dict[str, Any]) -> int | None:
    """Возвращает file_count для default apply-stage, если это можно определить безопасно."""
    try:
        applied_files = resolve_applied_files([], run_summary)
        git_snapshot = collect_git_snapshot(applied_files)
    except Exception:
        return None
    return git_snapshot["diff_summary"]["file_count"]


def _can_implement(run_summary: dict[str, Any], plan_payload: dict[str, Any], *, allow_empty_diff: bool) -> bool:
    """Проверяет, можно ли запускать apply-stage по реальным правилам."""
    try:
        ensure_apply_allowed(run_summary, plan_payload)
    except ValueError:
        return False
    diff_file_count = implementation_diff_count(run_summary)
    if diff_file_count is None:
        return allow_empty_diff
    if diff_file_count == 0 and not allow_empty_diff:
        return False
    return True


def build_status(run_dir: Path) -> dict[str, Any]:
    """Собирает итоговый статус run bundle."""
    summary_path = run_dir / "run-summary.json"
    plan_path = run_dir / "plan.json"
    approval_path = run_dir / "approval-checkpoints.json"
    execution_state_path = run_dir / "execution-state.json"
    approval_history_path = run_dir / "approval-history.json"
    verification_result_path = run_dir / "verification-result.json"
    sandbox_result_path = run_dir / "sandbox-result.json"
    review_result_path = run_dir / "review-result.json"
    approval_request_path = run_dir / "approval-request.json"
    commit_result_path = run_dir / "commit-result.json"
    push_result_path = run_dir / "push-result.json"
    close_result_path = run_dir / "close-result.json"

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
    review_payload = load_optional_json(review_result_path)
    approval_request_payload = load_optional_json(approval_request_path)
    commit_payload = load_optional_json(commit_result_path)
    push_payload = load_optional_json(push_result_path)
    close_payload = load_optional_json(close_result_path)

    artifact_status = collect_artifact_status(run_summary.get("artifacts", {}))
    plan_summary = summarize_plan(plan_payload)
    approval_summary = summarize_approval(approval_payload)
    action_blockers = build_action_blockers(
        run_summary=run_summary,
        plan_payload=plan_payload,
        approval_payload=approval_payload,
    )
    approval_history_summary = summarize_approval_history(approval_history)
    verification_summary = summarize_verification(verification_payload)
    sandbox_summary = summarize_sandbox(sandbox_payload)
    review_summary = summarize_review(review_payload)
    approval_request_summary = summarize_approval_request(approval_request_payload)
    commit_summary = summarize_commit(commit_payload)
    push_summary = summarize_push_execution(push_payload)
    close_summary = summarize_closure(close_payload)
    blockers = build_blockers(
        run_summary=run_summary,
        artifact_status=artifact_status,
        approval_summary=approval_summary,
        plan_summary=plan_summary,
        action_blockers=action_blockers,
    )
    readiness = build_readiness(
        run_summary=run_summary,
        plan_payload=plan_payload,
        approval_payload=approval_payload,
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
        "action_blockers": action_blockers,
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
    if review_summary is not None:
        output["review"] = review_summary
    if approval_request_summary is not None:
        output["approval_request"] = approval_request_summary
    if commit_summary is not None:
        output["commit"] = commit_summary
    if push_summary is not None:
        output["push_execution"] = push_summary
    if close_summary is not None:
        output["closure"] = close_summary

    return output


def render_human_status(status_payload: dict[str, Any]) -> str:
    """Рендерит короткий human-readable статус run bundle."""
    readiness = status_payload.get("readiness", {})
    action_blockers = status_payload.get("action_blockers", {})
    blockers = status_payload.get("blockers", [])
    plan = status_payload.get("plan", {})
    approval = status_payload.get("approval", {})

    lines: list[str] = [
        f"Run: {status_payload.get('run_id', 'unknown')}",
        f"State: {status_payload.get('status', 'unknown')} -> {status_payload.get('next_action', 'unknown')}",
        f"Task: {status_payload.get('task_type', {}).get('id', 'unknown')}",
    ]

    next_step = plan.get("next_pending_step")
    if next_step:
        lines.append(
            "Next plan step: "
            f"{next_step.get('id', 'unknown')} ({next_step.get('owner', 'unknown')})"
        )

    available_actions: list[str] = []
    if readiness.get("can_approve_run_checks"):
        available_actions.append("approve_run_checks")
    if readiness.get("can_implement"):
        available_actions.append("implement")
    elif readiness.get("can_implement_with_allow_empty_diff"):
        available_actions.append("implement_with_allow_empty_diff")
    if readiness.get("can_request_approval"):
        checkpoints = readiness.get("requestable_checkpoints", [])
        if checkpoints:
            available_actions.append(f"request_approval[{', '.join(checkpoints)}]")
    if readiness.get("can_request_commit_approval"):
        available_actions.append("request_commit_approval")
    if readiness.get("can_create_commit"):
        available_actions.append("create_commit")
    if readiness.get("can_request_push_approval"):
        available_actions.append("request_push_approval")
    if readiness.get("can_push"):
        available_actions.append("push")
    if readiness.get("can_close_run"):
        closable = readiness.get("closable_outcomes", [])
        if closable:
            available_actions.append(f"close_run[{', '.join(closable)}]")

    lines.append(
        "Available actions: "
        + (", ".join(available_actions) if available_actions else "none")
    )

    if approval.get("awaiting_approval"):
        lines.append("Awaiting approval: " + ", ".join(approval["awaiting_approval"]))

    if blockers:
        lines.append("Global blockers: " + ", ".join(blockers))
    else:
        lines.append("Global blockers: none")

    priority_actions = [
        "approve_run_checks",
        "implement",
        "request_approval",
        "create_commit",
        "push",
        "close_run",
    ]
    priority_lines: list[str] = []
    for action_name in priority_actions:
        action_reasons = action_blockers.get(action_name, [])
        if action_reasons:
            priority_lines.append(f"{action_name}: " + ", ".join(action_reasons[:3]))

    if priority_lines:
        lines.append("Action blockers:")
        lines.extend(f"- {line}" for line in priority_lines)

    return "\n".join(lines) + "\n"


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
        help="Базовая директория запусков (по умолчанию: runs).",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Печатать JSON с отступами.",
    )
    parser.add_argument(
        "--human",
        action="store_true",
        help="Печатать короткий человекочитаемый статус вместо JSON.",
    )
    return parser.parse_args()


def main() -> int:
    """Точка входа CLI."""
    args = parse_args()
    try:
        run_dir = resolve_run_dir(args)
        result = build_status(run_dir)
    except (FileNotFoundError, ValueError) as exc:
        if args.human:
            sys.stdout.write(f"Error: {exc}\n")
        else:
            json.dump(
                {"error": str(exc)},
                sys.stdout,
                ensure_ascii=False,
                indent=2 if args.pretty else None,
            )
            if args.pretty:
                sys.stdout.write("\n")
        return 1

    if args.human:
        sys.stdout.write(render_human_status(result))
        return 0

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
