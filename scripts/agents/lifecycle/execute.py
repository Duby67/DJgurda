#!/usr/bin/env python3
"""Выполнение первого автоматического этапа run bundle: загрузка контекста."""

from __future__ import annotations

import argparse
import json
import sys

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.config import ROOT


DEFAULT_RUNS_DIR = ROOT / "runs"
PLACEHOLDER_MARKERS = ("<", ">")
ABSTRACT_PREFIXES = (
    "tracked-docs-",
    "only-the-code-",
    "affected-",
    "helper-tests-",
    "isolated-",
)


def load_json(path: Path) -> dict[str, Any]:
    """Читает JSON-файл и возвращает объект."""
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Записывает JSON-файл на диск."""
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def checkpoint_status_map(approval_payload: dict[str, Any]) -> dict[str, str]:
    """Возвращает map checkpoint_id -> status."""
    return {
        item["id"]: item.get("status", "unknown")
        for item in approval_payload.get("checkpoints", [])
    }


def normalize_rel_path(value: str) -> str:
    """Нормализует относительный путь."""
    return value.strip().replace("\\", "/").lstrip("./")


def is_placeholder_or_abstract(value: str) -> bool:
    """Определяет, что элемент контекста не является прямым путем."""
    if any(marker in value for marker in PLACEHOLDER_MARKERS):
        return True
    return value.startswith(ABSTRACT_PREFIXES)


def safe_line_count(path: Path) -> int | None:
    """Возвращает количество строк для текстового файла, если это безопасно."""
    try:
        return len(path.read_text(encoding="utf-8").splitlines())
    except Exception:
        return None


def unresolved_item_payload(entry: dict[str, Any]) -> dict[str, Any]:
    """Оставляет компактную сводку по unresolved context item."""
    payload = {
        "category": entry.get("category"),
        "item": entry.get("item"),
        "kind": entry.get("kind"),
        "status": entry.get("status"),
        "blocking": entry.get("blocking", False),
    }
    if entry.get("reason"):
        payload["reason"] = entry["reason"]
    if entry.get("path"):
        payload["path"] = entry["path"]
    return payload


def is_blocking_unresolved(entry: dict[str, Any]) -> bool:
    """Определяет, должен ли unresolved context item блокировать run."""
    if entry.get("kind") != "missing":
        return False
    return entry.get("category") in {"agents", "docs", "code"}


def resolve_context_item(category: str, item: str) -> dict[str, Any]:
    """Разрешает один элемент context pack до состояния file/dir/missing/abstract."""
    normalized = normalize_rel_path(item)
    if is_placeholder_or_abstract(normalized):
        return {
            "category": category,
            "item": item,
            "kind": "abstract",
            "status": "unresolved",
            "reason": "placeholder_or_abstract_requirement",
            "blocking": False,
        }

    absolute = ROOT / normalized
    if absolute.is_file():
        return {
            "category": category,
            "item": item,
            "kind": "file",
            "status": "resolved",
            "path": normalized,
            "size_bytes": absolute.stat().st_size,
            "line_count": safe_line_count(absolute),
        }
    if absolute.is_dir():
        try:
            children = sorted(child.name for child in absolute.iterdir())
        except Exception:
            children = []
        return {
            "category": category,
            "item": item,
            "kind": "directory",
            "status": "resolved",
            "path": normalized,
            "child_count": len(children),
            "sample_children": children[:10],
        }
    return {
        "category": category,
        "item": item,
        "kind": "missing",
        "status": "missing",
        "path": normalized,
        "blocking": category in {"agents", "docs", "code"},
    }


def build_loaded_context(context_pack: dict[str, Any]) -> dict[str, Any]:
    """Собирает resolved representation для context pack."""
    categories = ["agents", "docs", "code", "tests"]
    resolved: dict[str, list[dict[str, Any]]] = {}
    summary = {
        "resolved_files": 0,
        "resolved_directories": 0,
        "abstract_items": 0,
        "missing_items": 0,
        "blocking_unresolved_items": 0,
        "advisory_unresolved_items": 0,
        "notes_count": len(context_pack.get("notes", [])),
    }
    unresolved_items: list[dict[str, Any]] = []

    for category in categories:
        items = context_pack.get(category, [])
        resolved_items = [resolve_context_item(category, item) for item in items]
        resolved[category] = resolved_items
        for entry in resolved_items:
            kind = entry["kind"]
            if kind == "file":
                summary["resolved_files"] += 1
            elif kind == "directory":
                summary["resolved_directories"] += 1
            elif kind == "abstract":
                summary["abstract_items"] += 1
                summary["advisory_unresolved_items"] += 1
                unresolved_items.append(unresolved_item_payload(entry))
            elif kind == "missing":
                summary["missing_items"] += 1
                if is_blocking_unresolved(entry):
                    summary["blocking_unresolved_items"] += 1
                else:
                    summary["advisory_unresolved_items"] += 1
                unresolved_items.append(unresolved_item_payload(entry))

    resolved["notes"] = [
        {
            "category": "notes",
            "kind": "note",
            "status": "informational",
            "text": item,
        }
        for item in context_pack.get("notes", [])
    ]

    return {
        "summary": summary,
        "unresolved_items": unresolved_items,
        "resolved": resolved,
    }


def render_context_summary_markdown(
    run_summary: dict[str, Any],
    loaded_context: dict[str, Any],
) -> str:
    """Рендерит человекочитаемую сводку по загруженному контексту."""
    summary = loaded_context["summary"]
    unresolved_items = loaded_context.get("unresolved_items", [])
    unresolved_block = "\n".join(
        f"- `{item.get('category', 'unknown')}` -> `{item.get('item', '')}`"
        f" ({item.get('kind', 'unknown')})"
        f"{' [blocking]' if item.get('blocking') else ' [advisory]'}"
        f"{': ' + item['reason'] if item.get('reason') else ''}"
        for item in unresolved_items
    ) or "- none"

    changed_paths = run_summary.get("changed_paths", [])
    changed_paths_block = "\n".join(f"- `{item}`" for item in changed_paths) or "- none"

    return (
        "# Context Summary\n\n"
        f"- Run ID: `{run_summary['run_id']}`\n"
        f"- Task Type: `{run_summary.get('task_type', {}).get('id', 'unknown')}`\n"
        f"- Resolved Files: {summary['resolved_files']}\n"
        f"- Resolved Directories: {summary['resolved_directories']}\n"
        f"- Abstract Items: {summary['abstract_items']}\n"
        f"- Missing Items: {summary['missing_items']}\n"
        f"- Blocking Unresolved: {summary['blocking_unresolved_items']}\n"
        f"- Advisory Unresolved: {summary['advisory_unresolved_items']}\n"
        f"- Notes: {summary['notes_count']}\n\n"
        "## Changed Paths\n\n"
        f"{changed_paths_block}\n\n"
        "## Unresolved Context\n\n"
        f"{unresolved_block}\n"
    )


def read_resolved_text_files(loaded_context: dict[str, Any], *, categories: tuple[str, ...]) -> list[dict[str, str]]:
    """Reads resolved text files from selected categories."""
    documents: list[dict[str, str]] = []
    for category in categories:
        for entry in loaded_context.get("resolved", {}).get(category, []):
            if entry.get("kind") != "file" or entry.get("status") != "resolved":
                continue
            rel_path = entry.get("path", "")
            if not rel_path:
                continue
            absolute = ROOT / rel_path
            try:
                text = absolute.read_text(encoding="utf-8")
            except Exception:
                continue
            documents.append(
                {
                    "category": category,
                    "path": rel_path,
                    "text": text,
                }
            )
    return documents


def extract_section_bullets(text: str) -> dict[str, list[str]]:
    """Extracts bullets grouped by markdown heading."""
    current_heading = "root"
    sections: dict[str, list[str]] = {current_heading: []}

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("#"):
            current_heading = stripped.lstrip("#").strip()
            sections.setdefault(current_heading, [])
            continue
        if stripped.startswith("- "):
            sections.setdefault(current_heading, []).append(stripped[2:].strip())

    return sections


def line_contains_negation(line: str) -> bool:
    """Detects whether a policy line expresses prohibition or negation."""
    normalized = f" {line.casefold()} "
    return any(
        token in normalized
        for token in (
            " do not ",
            " don't ",
            " does not ",
            " doesn't ",
            " must not ",
            " never ",
            " can't ",
            " cannot ",
            " not ",
            " не ",
            " нельзя ",
            " запрещ",
        )
    )


def contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    """Checks whether a normalized string contains any of the patterns."""
    return any(pattern in text for pattern in patterns)


def is_local_source_of_truth_conflict(line: str, *, has_negation: bool) -> bool:
    """Detects permissive local/ source-of-truth statements."""
    if "source of truth" not in line or "local/" not in line or has_negation:
        return False
    return contains_any(
        line,
        (
            "is source of truth",
            "are source of truth",
            "the source of truth",
            "является источником истины",
            "являются источником истины",
            "считать источником истины",
            "treat as source of truth",
            "considered source of truth",
        ),
    )


def is_tests_source_of_truth_conflict(line: str, *, has_negation: bool) -> bool:
    """Detects permissive tests-as-source-of-truth statements."""
    if "source of truth" not in line or "tests" not in line or has_negation:
        return False
    return contains_any(
        line,
        (
            "is source of truth",
            "are source of truth",
            "the source of truth",
            "являются источником истины",
            "считать источником истины",
            "treat as source of truth",
            "considered source of truth",
        ),
    )


def is_push_without_approval_conflict(line: str, *, has_negation: bool) -> bool:
    """Detects explicit permissions to push without approval."""
    if "push" not in line or has_negation:
        return False
    return contains_any(
        line,
        (
            "push without approval",
            "allow push without approval",
            "can push without approval",
            "можно push без approval",
            "можно push без подтвержд",
            "разрешен push без approval",
            "разрешен push без подтвержд",
        ),
    )


def detect_loaded_policy_conflicts(documents: list[dict[str, str]]) -> list[dict[str, str]]:
    """Detects simple policy conflicts inside loaded tracked docs."""
    conflicts: list[dict[str, str]] = []
    for document in documents:
        for line in document["text"].splitlines():
            normalized = line.casefold()
            has_negation = line_contains_negation(line)
            if is_local_source_of_truth_conflict(normalized, has_negation=has_negation):
                conflicts.append(
                    {
                        "path": document["path"],
                        "reason": "local_marked_as_source_of_truth",
                    }
                )
            if is_tests_source_of_truth_conflict(normalized, has_negation=has_negation):
                conflicts.append(
                    {
                        "path": document["path"],
                        "reason": "tests_marked_as_source_of_truth",
                    }
                )
            if is_push_without_approval_conflict(normalized, has_negation=has_negation):
                conflicts.append(
                    {
                        "path": document["path"],
                        "reason": "push_without_approval_rule_detected",
                    }
                )

    unique: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for conflict in conflicts:
        key = (conflict["path"], conflict["reason"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(conflict)
    return unique


def build_context_brief(
    *,
    loaded_context: dict[str, Any],
    run_summary: dict[str, Any],
    plan_payload: dict[str, Any],
) -> dict[str, Any]:
    """Builds a compact semantic brief for the loaded context."""
    documents = read_resolved_text_files(loaded_context, categories=("agents", "docs"))
    policy_conflicts = [
        {
            "path": "routing",
            "reason": reason,
        }
        for reason in run_summary.get("routing_diagnostics", {}).get("policy_conflicts", [])
    ]
    policy_conflicts.extend(detect_loaded_policy_conflicts(documents))

    constraints: list[str] = []
    invariants: list[str] = []
    adjacent_modules: list[str] = []
    risk_areas: list[str] = []

    for document in documents:
        sections = extract_section_bullets(document["text"])
        for heading, bullets in sections.items():
            lower_heading = heading.casefold()
            if any(token in lower_heading for token in ("constraint", "rule", "approval", "access", "security", "change rules", "context rules")):
                constraints.extend(bullets)
            if any(token in lower_heading for token in ("invariant", "stable contracts", "boundary", "key constraints")):
                invariants.extend(bullets)
            if "read next" in lower_heading:
                adjacent_modules.extend(bullets)
            if any(token in lower_heading for token in ("risk", "known gaps", "high-risk", "debt")):
                risk_areas.extend(bullets)

    unresolved_items = loaded_context.get("unresolved_items", [])
    open_questions = [
        f"Resolve context item: {item.get('item', '')}"
        for item in unresolved_items
        if item.get("blocking")
    ]
    open_questions.extend(
        f"Resolve policy conflict: {item['reason']}"
        for item in policy_conflicts
    )

    known_risks = plan_payload.get("known_risks", [])
    brief = {
        "constraints": list(dict.fromkeys(constraints))[:12],
        "invariants": list(dict.fromkeys(invariants))[:12],
        "known_risks": known_risks,
        "risk_areas": list(dict.fromkeys(risk_areas))[:12],
        "open_questions": list(dict.fromkeys(open_questions))[:12],
        "adjacent_modules": list(dict.fromkeys(adjacent_modules))[:12],
        "policy_conflicts": policy_conflicts,
        "context_gaps": unresolved_items,
        "active_initiatives": plan_payload.get("active_initiatives", []),
    }
    return brief


def update_plan_for_context_loaded(plan_payload: dict[str, Any]) -> dict[str, Any]:
    """Обновляет plan.json после загрузки контекста."""
    updated = json.loads(json.dumps(plan_payload, ensure_ascii=False))
    for step in updated.get("plan", []):
        if step.get("id") == "load_context":
            step["status"] = "completed"
        elif step.get("id") == "classify_task":
            step["status"] = "completed"
    return updated


def build_execution_state(
    run_summary: dict[str, Any],
    loaded_context: dict[str, Any],
    context_brief: dict[str, Any],
) -> dict[str, Any]:
    """Строит execution-state.json."""
    approval_payload = run_summary["approval"]
    needs_manual_review = approval_payload["needs_manual_review"]
    run_checks_status = checkpoint_status_map(approval_payload).get("run_checks", "awaiting_approval")
    routing_diagnostics = run_summary.get("routing_diagnostics", {})
    unresolved_context = loaded_context["summary"]["blocking_unresolved_items"] > 0
    policy_conflicts = context_brief.get("policy_conflicts", [])

    if routing_diagnostics.get("instruction_conflict", False):
        next_action = "resolve_instruction_conflict"
        status = "instruction_conflict"
    elif policy_conflicts:
        next_action = "resolve_instruction_conflict"
        status = "instruction_conflict"
    elif unresolved_context:
        next_action = "resolve_context_gaps"
        status = "context_insufficient"
    elif run_checks_status in {"approved", "not_required"}:
        next_action = "implement_change"
        status = "approved_for_implementation" if needs_manual_review or run_checks_status == "approved" else "context_loaded"
    elif needs_manual_review:
        next_action = "review_escalation_and_approve_implementation"
        status = "context_loaded_awaiting_manual_review"
    else:
        next_action = "approve_run_checks_before_implementation"
        status = "context_loaded_pending_run_checks_approval"

    return {
        "version": 1,
        "run_id": run_summary["run_id"],
        "phase": "context_loaded",
        "status": status,
        "next_action": next_action,
        "loaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "summary": loaded_context["summary"],
        "unresolved_items": loaded_context.get("unresolved_items", []),
        "routing_diagnostics": routing_diagnostics,
        "context_brief": context_brief,
        "approval": {
            "needs_manual_review": needs_manual_review,
            "escalation_reasons": approval_payload["escalation_reasons"],
            "checkpoint_statuses": checkpoint_status_map(approval_payload),
        },
    }


def resolve_run_dir(args: argparse.Namespace) -> Path:
    """Определяет директорию run bundle по аргументам."""
    if args.run_dir and args.run_id:
        raise ValueError("Нельзя одновременно использовать --run-dir и --run-id")

    if args.run_dir:
        return ROOT / normalize_rel_path(args.run_dir)
    if args.run_id:
        return (ROOT / normalize_rel_path(args.runs_dir)) / args.run_id.strip()
    raise ValueError("Нужно указать либо --run-dir, либо --run-id")


def build_output(run_dir: Path) -> dict[str, Any]:
    """Выполняет context loading для существующего run bundle."""
    plan_path = run_dir / "plan.json"
    context_pack_path = run_dir / "context-pack.json"
    summary_path = run_dir / "run-summary.json"

    if not plan_path.is_file():
        raise FileNotFoundError(f"Не найден файл: {plan_path}")
    if not context_pack_path.is_file():
        raise FileNotFoundError(f"Не найден файл: {context_pack_path}")
    if not summary_path.is_file():
        raise FileNotFoundError(f"Не найден файл: {summary_path}")

    plan_payload = load_json(plan_path)
    context_pack = load_json(context_pack_path)
    run_summary = load_json(summary_path)

    loaded_context = build_loaded_context(context_pack)
    context_brief = build_context_brief(
        loaded_context=loaded_context,
        run_summary=run_summary,
        plan_payload=plan_payload,
    )
    execution_state = build_execution_state(run_summary, loaded_context, context_brief)
    updated_plan = update_plan_for_context_loaded(plan_payload)

    loaded_context_path = run_dir / "loaded-context.json"
    execution_state_path = run_dir / "execution-state.json"
    context_brief_path = run_dir / "context-brief.json"
    context_summary_path = run_dir / "context-summary.md"

    write_json(loaded_context_path, loaded_context)
    write_json(execution_state_path, execution_state)
    write_json(context_brief_path, context_brief)
    context_summary_path.write_text(
        render_context_summary_markdown(run_summary, loaded_context),
        encoding="utf-8",
    )
    write_json(plan_path, updated_plan)

    artifacts = run_summary.setdefault("artifacts", {})
    run_summary["status"] = execution_state["status"]
    run_summary["next_action"] = execution_state["next_action"]
    artifacts["loaded_context"] = str(loaded_context_path.relative_to(ROOT)).replace("\\", "/")
    artifacts["execution_state"] = str(execution_state_path.relative_to(ROOT)).replace("\\", "/")
    artifacts["context_brief"] = str(context_brief_path.relative_to(ROOT)).replace("\\", "/")
    artifacts["context_summary"] = str(context_summary_path.relative_to(ROOT)).replace("\\", "/")
    run_summary["context"] = {
        "summary": loaded_context["summary"],
        "unresolved_items": loaded_context.get("unresolved_items", []),
        "brief": context_brief,
    }
    write_json(summary_path, run_summary)

    return {
        "run_id": run_summary["run_id"],
        "run_dir": str(run_dir.relative_to(ROOT)).replace("\\", "/"),
        "status": execution_state["status"],
        "next_action": execution_state["next_action"],
        "loaded_context_summary": loaded_context["summary"],
        "artifacts": run_summary["artifacts"],
    }


def parse_args() -> argparse.Namespace:
    """Парсит аргументы CLI."""
    parser = argparse.ArgumentParser(
        description="Загрузка context pack и обновление run bundle до execution state.",
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
    return parser.parse_args()


def main() -> int:
    """Точка входа CLI."""
    args = parse_args()
    run_dir = resolve_run_dir(args)
    result = build_output(run_dir)

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
