#!/usr/bin/env python3
"""Фиксирует review-stage внутри run bundle после verification/sandbox этапов."""

from __future__ import annotations

import argparse
import json
import sys

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_apply import REQUEST_APPROVAL_STEP_ID, REVIEW_STEP_ID
from agent_execute import DEFAULT_RUNS_DIR
from agent_route import ROOT


VALID_CONCLUSIONS = {"passed", "failed", "partial", "blocked"}


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
    """Считывает review summary."""
    if args.summary and args.summary_file:
        raise ValueError("Нельзя одновременно использовать --summary и --summary-file")
    if args.summary_file:
        return Path(args.summary_file).read_text(encoding="utf-8").strip()
    return (args.summary or "").strip()


def read_list_argument(values: list[str] | None, file_path: str | None) -> list[str]:
    """Считывает список строк из аргументов и/или файла."""
    result: list[str] = []
    if values:
        result.extend(item.strip() for item in values if item.strip())
    if file_path:
        raw_lines = Path(file_path).read_text(encoding="utf-8").splitlines()
        result.extend(line.strip() for line in raw_lines if line.strip())
    return result


def step_exists(plan_payload: dict[str, Any], step_id: str) -> bool:
    """Проверяет наличие шага в plan.json."""
    return any(step.get("id") == step_id for step in plan_payload.get("plan", []))


def ensure_review_allowed(run_summary: dict[str, Any], plan_payload: dict[str, Any]) -> None:
    """Проверяет, что lifecycle допускает review-stage."""
    if not step_exists(plan_payload, REVIEW_STEP_ID):
        raise ValueError("В plan.json отсутствует шаг review_result")

    allowed_statuses = {
        "verification_recorded_pending_review",
        "verification_partial_pending_review",
        "verification_skipped_pending_review",
        "sandbox_recorded_pending_review",
        "sandbox_partial_pending_review",
        "sandbox_skipped_pending_review",
        "review_failed",
        "review_blocked",
    }
    allowed_next_actions = {
        "review_result",
        "resolve_review_findings",
        "resolve_review_blockers",
    }

    if (
        run_summary.get("status") not in allowed_statuses
        and run_summary.get("next_action") not in allowed_next_actions
    ):
        raise ValueError("Review-stage можно запускать только после verification/sandbox этапов")


def derive_status_and_next_action(plan_payload: dict[str, Any], conclusion: str) -> tuple[str, str]:
    """Определяет новый status и next_action после review-stage."""
    if conclusion == "failed":
        return "review_failed", "resolve_review_findings"
    if conclusion == "blocked":
        return "review_blocked", "resolve_review_blockers"

    if step_exists(plan_payload, REQUEST_APPROVAL_STEP_ID):
        if conclusion == "partial":
            return "review_partial_pending_approval", "request_approval"
        return "review_passed_pending_approval", "request_approval"

    if conclusion == "partial":
        return "review_partial", "request_approval"
    return "review_passed", "request_approval"


def update_plan_for_review(plan_payload: dict[str, Any], conclusion: str) -> dict[str, Any]:
    """Обновляет шаг review_result в plan.json."""
    updated = clone_json_compatible(plan_payload)
    status_by_conclusion = {
        "passed": "completed",
        "partial": "completed",
        "failed": "failed",
        "blocked": "blocked",
    }

    for step in updated.get("plan", []):
        if step.get("id") == REVIEW_STEP_ID:
            step["status"] = status_by_conclusion[conclusion]
    return updated


def build_review_result(
    *,
    run_summary: dict[str, Any],
    conclusion: str,
    summary_text: str,
    reviewed_by: str,
    findings: list[str],
    risks: list[str],
) -> dict[str, Any]:
    """Строит review-result.json."""
    return {
        "version": 1,
        "run_id": run_summary["run_id"],
        "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
        "reviewed_by": reviewed_by,
        "conclusion": conclusion,
        "summary": summary_text,
        "findings": findings,
        "residual_risks": risks,
        "finding_count": len(findings),
        "risk_count": len(risks),
    }


def update_execution_state(
    execution_state: dict[str, Any] | None,
    *,
    status: str,
    next_action: str,
    review_result: dict[str, Any],
) -> dict[str, Any] | None:
    """Обновляет execution-state.json, если он существует."""
    if execution_state is None:
        return None

    updated = clone_json_compatible(execution_state)
    updated["phase"] = "review_recorded"
    updated["status"] = status
    updated["next_action"] = next_action
    updated["reviewed_at_utc"] = review_result["reviewed_at_utc"]
    updated["review"] = {
        "reviewed_by": review_result["reviewed_by"],
        "conclusion": review_result["conclusion"],
        "summary": review_result["summary"],
        "finding_count": review_result["finding_count"],
        "risk_count": review_result["risk_count"],
    }
    return updated


def build_output(
    run_dir: Path,
    *,
    conclusion: str,
    summary_text: str,
    reviewed_by: str,
    findings: list[str],
    risks: list[str],
) -> dict[str, Any]:
    """Фиксирует review-stage и обновляет run bundle."""
    summary_path = run_dir / "run-summary.json"
    plan_path = run_dir / "plan.json"
    execution_state_path = run_dir / "execution-state.json"
    review_result_path = run_dir / "review-result.json"

    if not summary_path.is_file():
        raise FileNotFoundError(f"Не найден файл: {summary_path}")
    if not plan_path.is_file():
        raise FileNotFoundError(f"Не найден файл: {plan_path}")

    run_summary = load_json(summary_path)
    plan_payload = load_json(plan_path)
    execution_state = load_json(execution_state_path) if execution_state_path.is_file() else None

    ensure_review_allowed(run_summary, plan_payload)

    review_result = build_review_result(
        run_summary=run_summary,
        conclusion=conclusion,
        summary_text=summary_text,
        reviewed_by=reviewed_by,
        findings=findings,
        risks=risks,
    )

    updated_plan = update_plan_for_review(plan_payload, conclusion)
    status, next_action = derive_status_and_next_action(updated_plan, conclusion)
    updated_execution_state = update_execution_state(
        execution_state,
        status=status,
        next_action=next_action,
        review_result=review_result,
    )

    artifacts = run_summary.setdefault("artifacts", {})
    artifacts["review_result"] = str(review_result_path.relative_to(ROOT)).replace("\\", "/")

    run_summary["status"] = status
    run_summary["next_action"] = next_action
    run_summary["artifacts"] = artifacts
    run_summary["review"] = {
        "reviewed_by": reviewed_by,
        "conclusion": conclusion,
        "summary": summary_text,
        "finding_count": len(findings),
        "risk_count": len(risks),
    }

    write_json(review_result_path, review_result)
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
        "finding_count": len(findings),
        "risk_count": len(risks),
        "artifacts": {
            "review_result": artifacts["review_result"],
        },
    }


def parse_args() -> argparse.Namespace:
    """Парсит аргументы CLI."""
    parser = argparse.ArgumentParser(
        description="Фиксация review-stage и запись review artifacts в run bundle.",
    )
    parser.add_argument("--run-dir", help="Путь к директории run bundle.")
    parser.add_argument("--run-id", help="Идентификатор запуска внутри runs-dir.")
    parser.add_argument(
        "--runs-dir",
        default=str(DEFAULT_RUNS_DIR.relative_to(ROOT)).replace("\\", "/"),
        help="Базовая директория запусков (по умолчанию: local/runs).",
    )
    parser.add_argument(
        "--conclusion",
        required=True,
        choices=sorted(VALID_CONCLUSIONS),
        help="Итог review-stage: passed, failed, partial или blocked.",
    )
    parser.add_argument("--summary", default="", help="Короткое описание review-stage.")
    parser.add_argument("--summary-file", help="Путь к файлу с описанием review-stage.")
    parser.add_argument("--reviewed-by", default="reviewer", help="Кто зафиксировал review-stage.")
    parser.add_argument(
        "--finding",
        action="append",
        help="Review finding. Можно передавать аргумент несколько раз.",
    )
    parser.add_argument("--findings-file", help="Путь к файлу со списком review findings, по одному на строку.")
    parser.add_argument(
        "--risk",
        action="append",
        help="Residual risk. Можно передавать аргумент несколько раз.",
    )
    parser.add_argument("--risks-file", help="Путь к файлу со списком residual risks, по одному на строку.")
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
            reviewed_by=args.reviewed_by.strip() or "reviewer",
            findings=read_list_argument(args.finding, args.findings_file),
            risks=read_list_argument(args.risk, args.risks_file),
        )
    except (FileNotFoundError, ValueError) as exc:
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
