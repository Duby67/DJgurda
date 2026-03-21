#!/usr/bin/env python3
"""Закрывает run bundle и формирует финальный отчет по lifecycle."""

from __future__ import annotations

import argparse
import json
import sys

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_execute import DEFAULT_RUNS_DIR
from agent_route import ROOT


VALID_OUTCOMES = {
    "completed",
    "completed_without_push",
    "cancelled",
    "failed",
}


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
    """Считывает close summary."""
    if args.summary and args.summary_file:
        raise ValueError("Нельзя одновременно использовать --summary и --summary-file")
    if args.summary_file:
        return Path(args.summary_file).read_text(encoding="utf-8").strip()
    return (args.summary or "").strip()


def read_notes(args: argparse.Namespace) -> list[str]:
    """Считывает заметки для финального закрытия."""
    notes: list[str] = []
    if args.note:
        notes.extend(item.strip() for item in args.note if item.strip())
    if args.notes_file:
        raw_lines = Path(args.notes_file).read_text(encoding="utf-8").splitlines()
        notes.extend(line.strip() for line in raw_lines if line.strip())
    return notes


def ensure_close_allowed(run_summary: dict[str, Any], outcome: str) -> None:
    """Проверяет, что run bundle можно закрыть выбранным outcome."""
    if run_summary.get("status") == "closed":
        raise ValueError("Run bundle уже закрыт")

    commit_created = bool(run_summary.get("commit", {}).get("commit_created"))
    push_created = bool(run_summary.get("push_execution", {}).get("push_created"))

    if outcome == "completed" and not push_created:
        raise ValueError("Outcome completed требует ранее выполненный реальный push")
    if outcome == "completed_without_push" and not commit_created:
        raise ValueError("Outcome completed_without_push требует ранее созданный реальный commit")


def build_closure_summary(run_summary: dict[str, Any]) -> dict[str, Any]:
    """Собирает компактную сводку состояния к моменту закрытия."""
    verification = run_summary.get("verification", {})
    sandbox = run_summary.get("sandbox", {})
    review = run_summary.get("review", {})
    commit = run_summary.get("commit", {})
    push_execution = run_summary.get("push_execution", {})

    return {
        "task_type": run_summary.get("task_type", {}),
        "changed_paths": run_summary.get("changed_paths", []),
        "verification_conclusion": verification.get("conclusion"),
        "sandbox_conclusion": sandbox.get("conclusion"),
        "review_conclusion": review.get("conclusion"),
        "commit_created": bool(commit.get("commit_created")),
        "commit_hash": commit.get("commit_hash"),
        "push_created": bool(push_execution.get("push_created")),
        "push_remote": push_execution.get("remote"),
        "push_branch": push_execution.get("branch"),
    }


def build_close_result(
    *,
    run_summary: dict[str, Any],
    outcome: str,
    closed_by: str,
    summary_text: str,
    notes: list[str],
) -> dict[str, Any]:
    """Строит close-result.json."""
    return {
        "version": 1,
        "run_id": run_summary["run_id"],
        "closed_at_utc": datetime.now(timezone.utc).isoformat(),
        "closed_by": closed_by,
        "outcome": outcome,
        "summary": summary_text,
        "notes": notes,
        "status_before_close": run_summary.get("status"),
        "next_action_before_close": run_summary.get("next_action"),
        "final_state": build_closure_summary(run_summary),
    }


def build_final_report(
    *,
    run_summary: dict[str, Any],
    close_result: dict[str, Any],
) -> str:
    """Строит human-facing final report markdown."""
    task_type = close_result["final_state"].get("task_type", {})
    changed_paths = close_result["final_state"].get("changed_paths", [])
    notes = close_result.get("notes", [])

    verification_conclusion = close_result["final_state"].get("verification_conclusion") or "not_recorded"
    sandbox_conclusion = close_result["final_state"].get("sandbox_conclusion") or "not_recorded"
    review_conclusion = close_result["final_state"].get("review_conclusion") or "not_recorded"
    commit_created = "yes" if close_result["final_state"].get("commit_created") else "no"
    push_created = "yes" if close_result["final_state"].get("push_created") else "no"
    commit_hash = close_result["final_state"].get("commit_hash") or "not_recorded"
    push_remote = close_result["final_state"].get("push_remote") or "not_recorded"
    push_branch = close_result["final_state"].get("push_branch") or "not_recorded"

    lines = [
        "# Final Report",
        "",
        close_result.get("summary") or "Финальный отчет сформирован без дополнительного текстового резюме.",
        "",
        "## Outcome",
        "",
        f"- `run_id`: `{run_summary['run_id']}`",
        f"- `outcome`: `{close_result['outcome']}`",
        f"- `closed_by`: `{close_result['closed_by']}`",
        f"- `closed_at_utc`: `{close_result['closed_at_utc']}`",
        f"- `status_before_close`: `{close_result['status_before_close']}`",
        f"- `next_action_before_close`: `{close_result['next_action_before_close']}`",
        f"- `task_type`: `{task_type.get('id', 'unknown')}`",
        "",
        "## Lifecycle",
        "",
        f"- Verification: `{verification_conclusion}`",
        f"- Sandbox: `{sandbox_conclusion}`",
        f"- Review: `{review_conclusion}`",
        f"- Commit created: `{commit_created}`",
        f"- Commit hash: `{commit_hash}`",
        f"- Push created: `{push_created}`",
        f"- Push remote: `{push_remote}`",
        f"- Push branch: `{push_branch}`",
        "",
        "## Scope",
        "",
    ]

    if changed_paths:
        lines.extend(f"- `{path}`" for path in changed_paths)
    else:
        lines.append("Измененные пути не были зафиксированы в run bundle.")

    lines.extend(["", "## Notes", ""])
    if notes:
        lines.extend(f"- {note}" for note in notes)
    else:
        lines.append("Дополнительные заметки отсутствуют.")

    return "\n".join(lines) + "\n"


def update_execution_state(
    execution_state: dict[str, Any] | None,
    *,
    close_result: dict[str, Any],
) -> dict[str, Any] | None:
    """Обновляет execution-state.json, если он существует."""
    if execution_state is None:
        return None

    updated = clone_json_compatible(execution_state)
    updated["phase"] = "closed"
    updated["status"] = "closed"
    updated["next_action"] = "none"
    updated["closed_at_utc"] = close_result["closed_at_utc"]
    updated["closure"] = {
        "outcome": close_result["outcome"],
        "closed_by": close_result["closed_by"],
        "summary": close_result["summary"],
        "notes": close_result["notes"],
    }
    return updated


def build_output(
    run_dir: Path,
    *,
    outcome: str,
    summary_text: str,
    closed_by: str,
    notes: list[str],
) -> dict[str, Any]:
    """Закрывает run bundle и записывает финальные артефакты."""
    summary_path = run_dir / "run-summary.json"
    execution_state_path = run_dir / "execution-state.json"
    close_result_path = run_dir / "close-result.json"
    final_report_path = run_dir / "final-report.md"

    if not summary_path.is_file():
        raise FileNotFoundError(f"Не найден файл: {summary_path}")

    run_summary = load_json(summary_path)
    execution_state = load_json(execution_state_path) if execution_state_path.is_file() else None

    ensure_close_allowed(run_summary, outcome)

    close_result = build_close_result(
        run_summary=run_summary,
        outcome=outcome,
        closed_by=closed_by,
        summary_text=summary_text,
        notes=notes,
    )
    final_report = build_final_report(
        run_summary=run_summary,
        close_result=close_result,
    )
    updated_execution_state = update_execution_state(
        execution_state,
        close_result=close_result,
    )

    artifacts = run_summary.setdefault("artifacts", {})
    artifacts["close_result"] = str(close_result_path.relative_to(ROOT)).replace("\\", "/")
    artifacts["final_report"] = str(final_report_path.relative_to(ROOT)).replace("\\", "/")

    run_summary["status"] = "closed"
    run_summary["next_action"] = "none"
    run_summary["artifacts"] = artifacts
    run_summary["closure"] = {
        "outcome": outcome,
        "closed_by": closed_by,
        "closed_at_utc": close_result["closed_at_utc"],
        "summary": summary_text,
        "notes": notes,
    }

    write_json(close_result_path, close_result)
    final_report_path.write_text(final_report, encoding="utf-8")
    if updated_execution_state is not None:
        write_json(execution_state_path, updated_execution_state)
    write_json(summary_path, run_summary)

    return {
        "run_id": run_summary["run_id"],
        "run_dir": str(run_dir.relative_to(ROOT)).replace("\\", "/"),
        "status": run_summary["status"],
        "next_action": run_summary["next_action"],
        "outcome": outcome,
        "artifacts": {
            "close_result": artifacts["close_result"],
            "final_report": artifacts["final_report"],
        },
    }


def parse_args() -> argparse.Namespace:
    """Парсит аргументы CLI."""
    parser = argparse.ArgumentParser(
        description="Закрытие run bundle и запись финального отчета.",
    )
    parser.add_argument("--run-dir", help="Путь к директории run bundle.")
    parser.add_argument("--run-id", help="Идентификатор запуска внутри runs-dir.")
    parser.add_argument(
        "--runs-dir",
        default=str(DEFAULT_RUNS_DIR.relative_to(ROOT)).replace("\\", "/"),
        help="Базовая директория запусков (по умолчанию: local/runs).",
    )
    parser.add_argument(
        "--outcome",
        required=True,
        choices=sorted(VALID_OUTCOMES),
        help="Итог закрытия run bundle.",
    )
    parser.add_argument("--summary", default="", help="Короткое описание результата закрытия.")
    parser.add_argument("--summary-file", help="Путь к файлу с описанием результата закрытия.")
    parser.add_argument("--closed-by", default="release_manager", help="Кто закрыл run bundle.")
    parser.add_argument(
        "--note",
        action="append",
        help="Дополнительная заметка для финального отчета. Можно передавать несколько раз.",
    )
    parser.add_argument("--notes-file", help="Путь к файлу со списком заметок, по одной на строку.")
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
            outcome=args.outcome,
            summary_text=read_summary(args),
            closed_by=args.closed_by.strip() or "release_manager",
            notes=read_notes(args),
        )
    except (FileNotFoundError, ValueError) as exc:
        json.dump(
            {
                "error": str(exc),
                "outcome": args.outcome,
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
