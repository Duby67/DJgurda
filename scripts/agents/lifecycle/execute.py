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
    }
    if entry.get("reason"):
        payload["reason"] = entry["reason"]
    if entry.get("path"):
        payload["path"] = entry["path"]
    return payload


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
                unresolved_items.append(unresolved_item_payload(entry))
            elif kind == "missing":
                summary["missing_items"] += 1
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
        f"- Notes: {summary['notes_count']}\n\n"
        "## Changed Paths\n\n"
        f"{changed_paths_block}\n\n"
        "## Unresolved Context\n\n"
        f"{unresolved_block}\n"
    )


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
) -> dict[str, Any]:
    """Строит execution-state.json."""
    approval_payload = run_summary["approval"]
    needs_manual_review = approval_payload["needs_manual_review"]
    run_checks_status = checkpoint_status_map(approval_payload).get("run_checks", "awaiting_approval")
    routing_diagnostics = run_summary.get("routing_diagnostics", {})
    unresolved_context = bool(
        loaded_context["summary"]["missing_items"] or loaded_context["summary"]["abstract_items"]
    )

    if routing_diagnostics.get("instruction_conflict", False):
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
    execution_state = build_execution_state(run_summary, loaded_context)
    updated_plan = update_plan_for_context_loaded(plan_payload)

    loaded_context_path = run_dir / "loaded-context.json"
    execution_state_path = run_dir / "execution-state.json"
    context_summary_path = run_dir / "context-summary.md"

    write_json(loaded_context_path, loaded_context)
    write_json(execution_state_path, execution_state)
    context_summary_path.write_text(
        render_context_summary_markdown(run_summary, loaded_context),
        encoding="utf-8",
    )
    write_json(plan_path, updated_plan)

    run_summary["status"] = execution_state["status"]
    run_summary["next_action"] = execution_state["next_action"]
    run_summary["artifacts"]["loaded_context"] = str(loaded_context_path.relative_to(ROOT)).replace("\\", "/")
    run_summary["artifacts"]["execution_state"] = str(execution_state_path.relative_to(ROOT)).replace("\\", "/")
    run_summary["artifacts"]["context_summary"] = str(context_summary_path.relative_to(ROOT)).replace("\\", "/")
    run_summary["context"] = {
        "summary": loaded_context["summary"],
        "unresolved_items": loaded_context.get("unresolved_items", []),
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
