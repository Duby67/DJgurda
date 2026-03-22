#!/usr/bin/env python3
"""Сбор полного run bundle для agent-first orchestration."""

from __future__ import annotations

import argparse
import json
import re
import sys

from datetime import datetime
from pathlib import Path
from typing import Any

from .plan import build_plan_output, write_artifacts
from .route import (
    CLASSIFIER_PATH,
    ROOT,
    ROUTING_PATH,
    build_output,
    load_json,
    read_paths,
    read_prompt,
)


DEFAULT_RUNS_DIR = ROOT / "runs"


def sanitize_run_id(value: str) -> str:
    """Приводит run_id к безопасному имени директории."""
    value = value.strip().replace("\\", "-").replace("/", "-")
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-._")
    return value or "run"


def generate_run_id(task_type_id: str) -> str:
    """Генерирует run_id по времени и task type."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return sanitize_run_id(f"{timestamp}-{task_type_id}")


def build_input_payload(prompt: str, paths: list[str]) -> dict[str, Any]:
    """Собирает входной payload запуска."""
    return {
        "prompt": prompt,
        "changed_paths": paths,
    }


def build_approval_checkpoints(route_result: dict[str, Any], plan_output: dict[str, Any]) -> dict[str, Any]:
    """Формирует approval checkpoints для run bundle."""
    tests_required = bool(route_result["context_pack"]["tests"])
    escalation_required = route_result["escalation"]["needed"]
    run_checks_required = tests_required or escalation_required

    if tests_required and escalation_required:
        run_checks_reason = "recommended tests or sandbox checks exist and manual review is required before implementation"
    elif tests_required:
        run_checks_reason = "recommended tests or sandbox checks exist for this task"
    elif escalation_required:
        run_checks_reason = "manual review is required before implementation"
    else:
        run_checks_reason = "no explicit checks required by routing map"

    checkpoints = [
        {
            "id": "run_checks",
            "required": run_checks_required,
            "status": "awaiting_approval" if run_checks_required else "not_required",
            "reason": run_checks_reason,
        },
        {
            "id": "commit",
            "required": True,
            "status": "awaiting_approval",
            "reason": "commit must always be explicitly approved by a human",
        },
        {
            "id": "push",
            "required": True,
            "status": "awaiting_approval",
            "reason": "push must always be explicitly approved by a human",
        },
    ]

    return {
        "needs_manual_review": escalation_required,
        "escalation_reasons": route_result["escalation"]["reasons"],
        "recommended_agents": plan_output["recommended_agents"],
        "checkpoints": checkpoints,
    }


def build_run_summary(
    run_id: str,
    route_result: dict[str, Any],
    plan_output: dict[str, Any],
    artifacts: dict[str, str],
) -> dict[str, Any]:
    """Собирает итоговую summary run bundle."""
    approval = build_approval_checkpoints(route_result, plan_output)
    instruction_conflict = route_result.get("routing_diagnostics", {}).get("instruction_conflict", False)

    if instruction_conflict:
        status = "instruction_conflict"
        next_action = "resolve_instruction_conflict"
    else:
        status = "awaiting_manual_review" if approval["needs_manual_review"] else "planned"
        next_action = "review_escalation" if approval["needs_manual_review"] else "load_context_and_implement"

    return {
        "run_id": run_id,
        "status": status,
        "next_action": next_action,
        "task_type": route_result["task_type"],
        "recommended_agents": plan_output["recommended_agents"],
        "changed_paths": route_result["changed_paths"],
        "routing_diagnostics": route_result.get("routing_diagnostics", {}),
        "verification_profile": plan_output.get("verification_profile", {}),
        "known_risks": plan_output.get("known_risks", []),
        "active_initiatives": plan_output.get("active_initiatives", []),
        "artifacts": artifacts,
        "approval": approval,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Записывает JSON на диск."""
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def build_run_bundle(
    prompt: str,
    paths: list[str],
    run_id: str,
    run_dir: Path,
) -> dict[str, Any]:
    """Создает полный run bundle и пишет артефакты на диск."""
    classifier = load_json(CLASSIFIER_PATH)
    routing = load_json(ROUTING_PATH)

    route_result = build_output(classifier=classifier, routing=routing, prompt=prompt, paths=paths)
    plan_output = build_plan_output(route_result)

    run_dir.mkdir(parents=True, exist_ok=True)
    input_path = run_dir / "input.json"
    write_json(input_path, build_input_payload(prompt, paths))

    artifacts = write_artifacts(run_dir, route_result, plan_output)
    artifacts["input"] = str(input_path.relative_to(ROOT)).replace("\\", "/")

    summary = build_run_summary(
        run_id=run_id,
        route_result=route_result,
        plan_output=plan_output,
        artifacts=artifacts,
    )
    summary_path = run_dir / "run-summary.json"
    approval_path = run_dir / "approval-checkpoints.json"
    write_json(summary_path, summary)
    write_json(approval_path, summary["approval"])

    artifacts["summary"] = str(summary_path.relative_to(ROOT)).replace("\\", "/")
    artifacts["approval"] = str(approval_path.relative_to(ROOT)).replace("\\", "/")
    summary["artifacts"] = artifacts

    write_json(summary_path, summary)

    return {
        "run_id": run_id,
        "run_dir": str(run_dir.relative_to(ROOT)).replace("\\", "/"),
        "route_result": route_result,
        "plan": plan_output,
        "summary": summary,
    }


def parse_args() -> argparse.Namespace:
    """Парсит аргументы CLI."""
    parser = argparse.ArgumentParser(
        description="Сбор полного run bundle для agent-first orchestration.",
    )
    parser.add_argument("--prompt", default="", help="Текст задачи или пользовательского запроса.")
    parser.add_argument("--prompt-file", help="Путь к файлу с текстом задачи.")
    parser.add_argument(
        "--path",
        action="append",
        help="Измененный путь. Можно передавать аргумент несколько раз.",
    )
    parser.add_argument("--paths-file", help="Путь к файлу со списком измененных путей, по одному на строку.")
    parser.add_argument(
        "--runs-dir",
        default=str(DEFAULT_RUNS_DIR.relative_to(ROOT)).replace("\\", "/"),
        help="Базовая директория для run bundles (по умолчанию: runs).",
    )
    parser.add_argument("--run-id", help="Явный run_id. Если не указан, будет сгенерирован автоматически.")
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Печатать итоговый JSON с отступами.",
    )
    return parser.parse_args()


def main() -> int:
    """Точка входа CLI."""
    args = parse_args()
    prompt = read_prompt(args)
    paths = read_paths(args)

    classifier = load_json(CLASSIFIER_PATH)
    routing = load_json(ROUTING_PATH)
    preview_route = build_output(classifier=classifier, routing=routing, prompt=prompt, paths=paths)

    run_id = sanitize_run_id(args.run_id) if args.run_id else generate_run_id(preview_route["task_type"]["id"])
    runs_dir = ROOT / normalize_runs_dir(args.runs_dir)
    run_dir = runs_dir / run_id

    result = build_run_bundle(prompt=prompt, paths=paths, run_id=run_id, run_dir=run_dir)

    json.dump(
        result,
        sys.stdout,
        ensure_ascii=False,
        indent=2 if args.pretty else None,
    )
    if args.pretty:
        sys.stdout.write("\n")
    return 0


def normalize_runs_dir(value: str) -> str:
    """Нормализует базовую директорию запусков."""
    return value.strip().replace("\\", "/").lstrip("./")


if __name__ == "__main__":
    raise SystemExit(main())
