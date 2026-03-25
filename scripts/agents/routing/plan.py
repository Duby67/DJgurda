#!/usr/bin/env python3
"""Построение swarm-плана и артефактов поверх route-результата."""

from __future__ import annotations

import argparse
import json
import sys

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.agents.knowledge import (
    collect_active_initiatives,
    collect_known_risks,
    get_verification_profile,
)

from .route import (
    CLASSIFIER_PATH,
    ROOT,
    ROUTING_PATH,
    build_output,
    load_json,
    read_paths,
    read_prompt,
    unique_keep_order,
)


@dataclass(frozen=True)
class PlanStep:
    """Описание одного шага swarm-плана."""

    step_id: str
    title: str
    owner: str
    status: str
    details: list[str]

    def to_dict(self) -> dict[str, Any]:
        """Преобразует шаг к сериализуемому виду."""
        return {
            "id": self.step_id,
            "title": self.title,
            "owner": self.owner,
            "status": self.status,
            "details": self.details,
        }


def infer_agent_roles(route_result: dict[str, Any]) -> list[str]:
    """Определяет рекомендуемые agent roles."""
    verification_profile = get_verification_profile(route_result["task_type"]["id"])
    has_profile_checks = bool(
        verification_profile.get("required_checks") or verification_profile.get("optional_checks")
    )
    has_profile_commands = bool(verification_profile.get("allowed_commands"))
    roles = [
        "planner",
        "context_loader",
        "coder",
        "reviewer",
    ]

    if route_result["context_pack"]["tests"] or has_profile_checks:
        roles.append("tester")

    if (
        route_result["task_type"]["id"] == "deploy_or_infra_change"
        or route_result["task_type"]["id"] == "release_or_versioning_change"
        or route_result["escalation"]["needed"]
    ):
        roles.append("release_manager")

    if has_profile_commands or route_result["context_pack"]["tests"] or route_result["task_type"]["id"] in {
        "deploy_or_infra_change",
        "test_harness_or_smoke_setup_change",
    }:
        roles.append("sandbox_runner")

    return unique_keep_order(roles)


def build_step_details_from_list(prefix: str, items: list[str]) -> list[str]:
    """Формирует человекочитаемые детали шага из списка строк."""
    return [f"{prefix}: {item}" for item in items]


def build_planning_context(route_result: dict[str, Any]) -> dict[str, Any]:
    """Собирает planning inputs из verification policy, plans и backlog."""
    task_type_id = route_result["task_type"]["id"]
    changed_paths = route_result["changed_paths"]
    verification_profile = get_verification_profile(task_type_id)
    known_risks = collect_known_risks(changed_paths, task_type_id)
    active_initiatives = collect_active_initiatives(changed_paths, task_type_id)
    return {
        "verification_profile": verification_profile,
        **known_risks,
        **active_initiatives,
    }


def build_plan_steps(route_result: dict[str, Any], planning_context: dict[str, Any]) -> list[PlanStep]:
    """Строит список шагов swarm-плана."""
    context_pack = route_result["context_pack"]
    tests = context_pack["tests"]
    escalation = route_result["escalation"]
    verification_profile = planning_context["verification_profile"]
    known_risks = planning_context.get("known_risks", [])
    active_initiatives = planning_context.get("active_initiatives", [])
    has_profile_checks = bool(
        verification_profile.get("required_checks") or verification_profile.get("optional_checks")
    )
    has_profile_commands = bool(verification_profile.get("allowed_commands"))

    steps: list[PlanStep] = [
        PlanStep(
            step_id="classify_task",
            title="Classify Task",
            owner="planner",
            status="completed",
            details=[
                f"selected task type: {route_result['task_type']['id']}",
                *build_step_details_from_list("evidence", [
                    entry["id"] for entry in route_result["matched_task_types"]
                ]),
            ],
        ),
        PlanStep(
            step_id="load_context",
            title="Load Context Pack",
            owner="context_loader",
            status="pending",
            details=(
                build_step_details_from_list("read agent policy", context_pack["agents"])
                + build_step_details_from_list("read documentation", context_pack["docs"])
                + build_step_details_from_list("inspect code", context_pack["code"])
            ),
        ),
        PlanStep(
            step_id="implement_change",
            title="Implement Change",
            owner="coder",
            status="pending",
            details=[
                f"work inside task type: {route_result['task_type']['label']}",
                f"verification risk level: {verification_profile['risk_level']}",
                *build_step_details_from_list("respect note", context_pack["notes"]),
                *build_step_details_from_list("known risk", [item["title"] for item in known_risks]),
                *build_step_details_from_list("active initiative", [item["path"] for item in active_initiatives]),
            ],
        ),
    ]

    if tests or has_profile_checks:
        steps.append(
            PlanStep(
                step_id="verify_change",
                title="Verify Change",
                owner="tester",
                status="pending",
                details=(
                    build_step_details_from_list("recommended check", tests)
                    + build_step_details_from_list("required profile check", verification_profile["required_checks"])
                    + build_step_details_from_list("optional profile check", verification_profile["optional_checks"])
                    + build_step_details_from_list("allowed command", verification_profile["allowed_commands"])
                ),
            )
        )

    if tests or has_profile_commands or route_result["task_type"]["id"] in {
        "deploy_or_infra_change",
        "test_harness_or_smoke_setup_change",
    }:
        steps.append(
            PlanStep(
                step_id="run_in_sandbox",
                title="Run In Sandbox",
                owner="sandbox_runner",
                status="pending",
                details=[
                    "use isolated execution for environment-sensitive checks when needed",
                    "collect logs, machine-readable reports, and failure artifacts",
                ],
            )
        )

    steps.append(
        PlanStep(
            step_id="review_result",
            title="Review Result",
            owner="reviewer",
            status="pending",
            details=[
                "check contract consistency",
                "check scope control",
                "check docs alignment",
                "check residual risks",
                *build_step_details_from_list("known risk", [item["title"] for item in known_risks]),
            ],
        )
    )

    if escalation["needed"]:
        steps.append(
            PlanStep(
                step_id="manual_review",
                title="Manual Review",
                owner="release_manager",
                status="pending",
                details=(
                    build_step_details_from_list("escalation reason", escalation["reasons"])
                    + build_step_details_from_list("known risk", [item["title"] for item in known_risks])
                ),
            )
        )

    steps.append(
        PlanStep(
            step_id="request_approval",
            title="Request Approval",
            owner="release_manager" if escalation["needed"] else "planner",
            status="pending",
            details=[
                "show changed files, recommended checks, and residual risks",
                "request approval for commit",
                "request approval for push separately if needed",
            ],
        )
    )

    return steps


def build_plan_output(route_result: dict[str, Any]) -> dict[str, Any]:
    """Собирает итоговый swarm-plan JSON."""
    roles = infer_agent_roles(route_result)
    planning_context = build_planning_context(route_result)
    steps = build_plan_steps(route_result, planning_context)
    return {
        "version": 1,
        "task_type": route_result["task_type"],
        "changed_paths": route_result["changed_paths"],
        "context_expansion": route_result.get("context_expansion", {}),
        "recommended_agents": roles,
        "context_pack": route_result["context_pack"],
        "escalation": route_result["escalation"],
        "verification_profile": planning_context["verification_profile"],
        "known_risks": planning_context.get("known_risks", []),
        "risk_sources": planning_context.get("risk_sources", []),
        "active_initiatives": planning_context.get("active_initiatives", []),
        "active_initiative_sources": planning_context.get("active_initiative_sources", []),
        "plan": [step.to_dict() for step in steps],
    }


def write_artifacts(output_dir: Path, route_result: dict[str, Any], plan_output: dict[str, Any]) -> dict[str, str]:
    """Записывает plan/context artifacts на диск."""
    output_dir.mkdir(parents=True, exist_ok=True)
    context_pack_path = output_dir / "context-pack.json"
    context_trace_path = output_dir / "context-trace.json"
    route_result_path = output_dir / "route-result.json"
    plan_path = output_dir / "plan.json"

    context_pack_path.write_text(
        json.dumps(route_result["context_pack"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    context_trace_path.write_text(
        json.dumps(route_result.get("context_trace", []), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    route_result_path.write_text(
        json.dumps(route_result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    plan_path.write_text(
        json.dumps(plan_output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    return {
        "context_pack": str(context_pack_path.relative_to(ROOT)).replace("\\", "/"),
        "context_trace": str(context_trace_path.relative_to(ROOT)).replace("\\", "/"),
        "route_result": str(route_result_path.relative_to(ROOT)).replace("\\", "/"),
        "plan": str(plan_path.relative_to(ROOT)).replace("\\", "/"),
    }


def parse_args() -> argparse.Namespace:
    """Парсит аргументы CLI."""
    parser = argparse.ArgumentParser(
        description="Построение swarm-плана на основе route-классификации.",
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
        "--output-dir",
        help="Каталог для записи артефактов plan/context-pack/route-result.",
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
    prompt = read_prompt(args)
    paths = read_paths(args)

    classifier = load_json(CLASSIFIER_PATH)
    routing = load_json(ROUTING_PATH)
    route_result = build_output(classifier=classifier, routing=routing, prompt=prompt, paths=paths)
    plan_output = build_plan_output(route_result)

    if args.output_dir:
        written = write_artifacts(ROOT / args.output_dir, route_result, plan_output)
        plan_output["artifacts"] = written

    json.dump(
        plan_output,
        sys.stdout,
        ensure_ascii=False,
        indent=2 if args.pretty else None,
    )
    if args.pretty:
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
