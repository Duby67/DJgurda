#!/usr/bin/env python3
"""Фиксирует approval-request stage и собирает approval packet для человека."""

from __future__ import annotations

import argparse
import json
import sys

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .approve import COMMIT_ID, PUSH_ID
from .apply import REQUEST_APPROVAL_STEP_ID
from .execute import DEFAULT_RUNS_DIR
from scripts.config import ROOT


VALID_CHECKPOINTS = {COMMIT_ID, PUSH_ID}


def load_json(path: Path) -> dict[str, Any]:
    """Читает JSON-файл."""
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    """Записывает JSON-файл."""
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_optional_json(path: Path) -> dict[str, Any] | None:
    """Читает optional JSON-файл, если он существует."""
    if not path.is_file():
        return None
    return load_json(path)


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
    """Считывает approval-request summary."""
    if args.summary and args.summary_file:
        raise ValueError("Нельзя одновременно использовать --summary и --summary-file")
    if args.summary_file:
        return Path(args.summary_file).read_text(encoding="utf-8").strip()
    return (args.summary or "").strip()


def read_requested_checkpoints(args: argparse.Namespace, approval_payload: dict[str, Any]) -> list[str]:
    """Определяет, какие checkpoint'ы нужно запросить у пользователя."""
    if args.checkpoint:
        checkpoints = [item.strip() for item in args.checkpoint if item.strip()]
    else:
        statuses = checkpoint_status_map(approval_payload)
        if statuses.get(COMMIT_ID) == "awaiting_approval":
            checkpoints = [COMMIT_ID]
        elif statuses.get(COMMIT_ID) == "approved" and statuses.get(PUSH_ID) == "awaiting_approval":
            checkpoints = [PUSH_ID]
        else:
            checkpoints = [
                item.get("id", "")
                for item in approval_payload.get("checkpoints", [])
                if item.get("required", True)
                and item.get("status") == "awaiting_approval"
                and item.get("id") in VALID_CHECKPOINTS
            ]

    unique: list[str] = []
    seen: set[str] = set()
    for checkpoint_id in checkpoints:
        if checkpoint_id not in VALID_CHECKPOINTS:
            raise ValueError(
                f"Неподдерживаемый checkpoint '{checkpoint_id}'. Допустимо: {sorted(VALID_CHECKPOINTS)}",
            )
        if checkpoint_id in seen:
            continue
        seen.add(checkpoint_id)
        unique.append(checkpoint_id)

    if not unique:
        raise ValueError("Не найдено checkpoint'ов для approval request")

    return unique


def step_exists(plan_payload: dict[str, Any], step_id: str) -> bool:
    """Проверяет наличие шага в plan.json."""
    return any(step.get("id") == step_id for step in plan_payload.get("plan", []))


def checkpoint_status_map(approval_payload: dict[str, Any]) -> dict[str, str]:
    """Возвращает map checkpoint_id -> status."""
    return {
        item["id"]: item.get("status", "unknown")
        for item in approval_payload.get("checkpoints", [])
    }


def ensure_request_allowed(
    run_summary: dict[str, Any],
    plan_payload: dict[str, Any],
    approval_payload: dict[str, Any],
    requested_checkpoints: list[str],
) -> None:
    """Проверяет, что lifecycle допускает approval-request stage."""
    if not step_exists(plan_payload, REQUEST_APPROVAL_STEP_ID):
        raise ValueError("В plan.json отсутствует шаг request_approval")

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
        raise ValueError("Approval-request stage можно запускать только после review-stage")

    statuses = checkpoint_status_map(approval_payload)
    if PUSH_ID in requested_checkpoints and statuses.get(COMMIT_ID) != "approved":
        raise ValueError("Нельзя запрашивать push approval до approve checkpoint 'commit'")
    if PUSH_ID in requested_checkpoints:
        commit_result_rel = run_summary.get("artifacts", {}).get("commit_result", "")
        if not commit_result_rel or not (ROOT / normalize_rel_path(commit_result_rel)).is_file():
            raise ValueError("Нельзя запрашивать push approval до фиксации commit-stage")
        if not run_summary.get("commit", {}).get("commit_created", False):
            raise ValueError("Нельзя запрашивать push approval до создания реального commit")

    for checkpoint_id in requested_checkpoints:
        status = statuses.get(checkpoint_id)
        if status not in {"awaiting_approval", "approved"}:
            raise ValueError(
                f"Checkpoint '{checkpoint_id}' находится в состоянии '{status}' и не готов к approval request",
            )


def summarize_checkpoints(
    approval_payload: dict[str, Any],
    requested_checkpoints: list[str],
) -> list[dict[str, Any]]:
    """Собирает детальную сводку по requested checkpoints."""
    by_id = {
        item["id"]: item
        for item in approval_payload.get("checkpoints", [])
    }
    summary: list[dict[str, Any]] = []
    for checkpoint_id in requested_checkpoints:
        checkpoint = by_id[checkpoint_id]
        summary.append(
            {
                "id": checkpoint_id,
                "status": checkpoint.get("status", "unknown"),
                "required": checkpoint.get("required", True),
                "reason": checkpoint.get("reason", ""),
            }
        )
    return summary


def build_artifact_snapshot(run_summary: dict[str, Any]) -> dict[str, str]:
    """Оставляет в packet только доступные run artifacts."""
    artifacts = run_summary.get("artifacts", {})
    snapshot: dict[str, str] = {}
    for key, rel_path in artifacts.items():
        full_path = ROOT / normalize_rel_path(rel_path)
        if full_path.exists():
            snapshot[key] = rel_path
    return snapshot


def build_approval_request_packet(
    *,
    run_summary: dict[str, Any],
    approval_payload: dict[str, Any],
    requested_checkpoints: list[str],
    summary_text: str,
    requested_by: str,
    implementation_payload: dict[str, Any] | None,
    verification_payload: dict[str, Any] | None,
    sandbox_payload: dict[str, Any] | None,
    review_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    """Строит approval-request.json."""
    review = review_payload or run_summary.get("review", {})
    verification = verification_payload or run_summary.get("verification", {})
    sandbox = sandbox_payload or run_summary.get("sandbox", {})
    implementation = implementation_payload or run_summary.get("implementation", {})

    return {
        "version": 1,
        "run_id": run_summary["run_id"],
        "requested_at_utc": datetime.now(timezone.utc).isoformat(),
        "requested_by": requested_by,
        "summary": summary_text,
        "task_type": run_summary.get("task_type", {}),
        "requested_checkpoints": requested_checkpoints,
        "checkpoint_details": summarize_checkpoints(approval_payload, requested_checkpoints),
        "changed_paths": run_summary.get("changed_paths", []),
        "context": run_summary.get("context", {}),
        "changed_files": run_summary.get("changed_files", {}),
        "implementation": implementation,
        "verification": verification,
        "sandbox": sandbox,
        "review": review,
        "artifacts": build_artifact_snapshot(run_summary),
    }


def render_markdown_packet(packet: dict[str, Any]) -> str:
    """Рендерит человекочитаемый markdown approval packet."""
    requested = ", ".join(packet.get("requested_checkpoints", [])) or "-"
    changed_paths = packet.get("changed_paths", [])
    changed_paths_block = "\n".join(f"- `{item}`" for item in changed_paths) or "- none"

    checkpoint_lines = []
    for item in packet.get("checkpoint_details", []):
        checkpoint_lines.append(
            f"- `{item['id']}`: status=`{item['status']}`, reason={item.get('reason', '') or '-'}"
        )
    checkpoints_block = "\n".join(checkpoint_lines) or "- none"

    residual_risks = packet.get("review", {}).get("risk_count", 0)
    residual_risk_lines = packet.get("review", {}).get("residual_risks", [])
    risks_block = "\n".join(f"- {item}" for item in residual_risk_lines) or "- none"
    context_summary = packet.get("context", {}).get("summary", {})
    unresolved_items = packet.get("context", {}).get("unresolved_items", [])
    unresolved_block = "\n".join(
        f"- `{item.get('category', 'unknown')}` -> `{item.get('item', '')}`"
        for item in unresolved_items
    ) or "- none"
    changed_files = packet.get("changed_files", {}).get("changed_files", [])
    changed_files_block = "\n".join(f"- `{item}`" for item in changed_files) or "- none"

    artifact_lines = "\n".join(
        f"- `{key}`: `{value}`"
        for key, value in packet.get("artifacts", {}).items()
    ) or "- none"

    return (
        "# Approval Request\n\n"
        f"- Run ID: `{packet['run_id']}`\n"
        f"- Task Type: `{packet.get('task_type', {}).get('id', 'unknown')}`\n"
        f"- Requested By: `{packet.get('requested_by', 'unknown')}`\n"
        f"- Requested At UTC: `{packet.get('requested_at_utc', '')}`\n"
        f"- Requested Checkpoints: {requested}\n"
        f"- Summary: {packet.get('summary', '') or '-'}\n\n"
        "## Changed Paths\n\n"
        f"{changed_paths_block}\n\n"
        "## Requested Checkpoints\n\n"
        f"{checkpoints_block}\n\n"
        "## Context\n\n"
        f"- Resolved Files: {context_summary.get('resolved_files', 0)}\n"
        f"- Resolved Directories: {context_summary.get('resolved_directories', 0)}\n"
        f"- Abstract Items: {context_summary.get('abstract_items', 0)}\n"
        f"- Missing Items: {context_summary.get('missing_items', 0)}\n"
        f"{unresolved_block}\n\n"
        "## Changed Files\n\n"
        f"{changed_files_block}\n\n"
        "## Implementation\n\n"
        f"- Summary: {packet.get('implementation', {}).get('summary', '') or '-'}\n"
        f"- Applied Files: {packet.get('implementation', {}).get('applied_files', []) or '-'}\n\n"
        "## Verification\n\n"
        f"- Conclusion: {packet.get('verification', {}).get('conclusion', '-')}\n"
        f"- Check Summary: {packet.get('verification', {}).get('check_summary', {}) or '-'}\n\n"
        "## Sandbox\n\n"
        f"- Conclusion: {packet.get('sandbox', {}).get('conclusion', '-')}\n"
        f"- Environment: {packet.get('sandbox', {}).get('environment', '-')}\n"
        f"- Sandbox Ref: {packet.get('sandbox', {}).get('sandbox_ref', '') or '-'}\n\n"
        "## Review\n\n"
        f"- Conclusion: {packet.get('review', {}).get('conclusion', '-')}\n"
        f"- Findings: {packet.get('review', {}).get('finding_count', 0)}\n"
        f"- Residual Risks: {residual_risks}\n"
        f"{risks_block}\n\n"
        "## Artifacts\n\n"
        f"{artifact_lines}\n"
    )


def update_plan_for_request(plan_payload: dict[str, Any]) -> dict[str, Any]:
    """Помечает request_approval как завершенный."""
    updated = clone_json_compatible(plan_payload)
    for step in updated.get("plan", []):
        if step.get("id") == REQUEST_APPROVAL_STEP_ID:
            step["status"] = "completed"
    return updated


def derive_status_and_next_action(requested_checkpoints: list[str]) -> tuple[str, str]:
    """Определяет status и next_action после формирования approval packet."""
    if COMMIT_ID in requested_checkpoints:
        return "awaiting_commit_approval", "await_commit_approval"
    if PUSH_ID in requested_checkpoints:
        return "awaiting_push_approval", "await_push_approval"
    return "approval_request_recorded", "await_manual_approval"


def update_execution_state(
    execution_state: dict[str, Any] | None,
    *,
    status: str,
    next_action: str,
    approval_request: dict[str, Any],
) -> dict[str, Any] | None:
    """Обновляет execution-state.json, если он существует."""
    if execution_state is None:
        return None

    updated = clone_json_compatible(execution_state)
    updated["phase"] = "approval_requested"
    updated["status"] = status
    updated["next_action"] = next_action
    updated["approval_requested_at_utc"] = approval_request["requested_at_utc"]
    updated["approval_request"] = {
        "requested_by": approval_request["requested_by"],
        "requested_checkpoints": approval_request["requested_checkpoints"],
        "summary": approval_request["summary"],
    }
    return updated


def build_output(
    run_dir: Path,
    *,
    requested_by: str,
    summary_text: str,
    requested_checkpoints: list[str] | None,
) -> dict[str, Any]:
    """Фиксирует approval-request stage и обновляет run bundle."""
    summary_path = run_dir / "run-summary.json"
    plan_path = run_dir / "plan.json"
    execution_state_path = run_dir / "execution-state.json"
    approval_path = run_dir / "approval-checkpoints.json"
    request_json_path = run_dir / "approval-request.json"
    request_md_path = run_dir / "approval-request.md"
    apply_result_path = run_dir / "apply-result.json"
    verification_result_path = run_dir / "verification-result.json"
    sandbox_result_path = run_dir / "sandbox-result.json"
    review_result_path = run_dir / "review-result.json"

    if not summary_path.is_file():
        raise FileNotFoundError(f"Не найден файл: {summary_path}")
    if not plan_path.is_file():
        raise FileNotFoundError(f"Не найден файл: {plan_path}")
    if not approval_path.is_file():
        raise FileNotFoundError(f"Не найден файл: {approval_path}")

    run_summary = load_json(summary_path)
    plan_payload = load_json(plan_path)
    approval_payload = load_json(approval_path)
    execution_state = load_json(execution_state_path) if execution_state_path.is_file() else None
    apply_result = load_optional_json(apply_result_path)
    verification_result = load_optional_json(verification_result_path)
    sandbox_result = load_optional_json(sandbox_result_path)
    review_result = load_optional_json(review_result_path)

    checkpoints = requested_checkpoints or read_requested_checkpoints(
        argparse.Namespace(checkpoint=None),
        approval_payload,
    )
    ensure_request_allowed(run_summary, plan_payload, approval_payload, checkpoints)

    approval_request = build_approval_request_packet(
        run_summary=run_summary,
        approval_payload=approval_payload,
        requested_checkpoints=checkpoints,
        summary_text=summary_text,
        requested_by=requested_by,
        implementation_payload=apply_result,
        verification_payload=verification_result,
        sandbox_payload=sandbox_result,
        review_payload=review_result,
    )
    approval_markdown = render_markdown_packet(approval_request)

    updated_plan = update_plan_for_request(plan_payload)
    status, next_action = derive_status_and_next_action(checkpoints)
    updated_execution_state = update_execution_state(
        execution_state,
        status=status,
        next_action=next_action,
        approval_request=approval_request,
    )

    artifacts = run_summary.setdefault("artifacts", {})
    artifacts["approval_request"] = str(request_json_path.relative_to(ROOT)).replace("\\", "/")
    artifacts["approval_request_markdown"] = str(request_md_path.relative_to(ROOT)).replace("\\", "/")

    run_summary["status"] = status
    run_summary["next_action"] = next_action
    run_summary["artifacts"] = artifacts
    run_summary["approval_request"] = {
        "requested_by": requested_by,
        "summary": summary_text,
        "requested_checkpoints": checkpoints,
    }

    write_json(request_json_path, approval_request)
    request_md_path.write_text(approval_markdown, encoding="utf-8")
    write_json(plan_path, updated_plan)
    if updated_execution_state is not None:
        write_json(execution_state_path, updated_execution_state)
    write_json(summary_path, run_summary)

    return {
        "run_id": run_summary["run_id"],
        "run_dir": str(run_dir.relative_to(ROOT)).replace("\\", "/"),
        "status": status,
        "next_action": next_action,
        "requested_checkpoints": checkpoints,
        "artifacts": {
            "approval_request": artifacts["approval_request"],
            "approval_request_markdown": artifacts["approval_request_markdown"],
        },
    }


def parse_args() -> argparse.Namespace:
    """Парсит аргументы CLI."""
    parser = argparse.ArgumentParser(
        description="Фиксация approval-request stage и сбор approval packet для человека.",
    )
    parser.add_argument("--run-dir", help="Путь к директории run bundle.")
    parser.add_argument("--run-id", help="Идентификатор запуска внутри runs-dir.")
    parser.add_argument(
        "--runs-dir",
        default=str(DEFAULT_RUNS_DIR.relative_to(ROOT)).replace("\\", "/"),
        help="Базовая директория запусков (по умолчанию: runs).",
    )
    parser.add_argument(
        "--checkpoint",
        action="append",
        help="Какой checkpoint запросить у пользователя. Можно передавать несколько раз.",
    )
    parser.add_argument("--summary", default="", help="Короткое описание approval request.")
    parser.add_argument("--summary-file", help="Путь к файлу с описанием approval request.")
    parser.add_argument("--requested-by", default="release_manager", help="Кто сформировал approval request.")
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
            requested_by=args.requested_by.strip() or "release_manager",
            summary_text=read_summary(args),
            requested_checkpoints=[item.strip() for item in args.checkpoint] if args.checkpoint else None,
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
