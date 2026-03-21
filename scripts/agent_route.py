#!/usr/bin/env python3
"""Классификация задач и сбор context pack для agent-first orchestration."""

from __future__ import annotations

import argparse
import json
import sys

from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
CLASSIFIER_PATH = ROOT / "docs" / "agent-task-classifier.json"
ROUTING_PATH = ROOT / "docs" / "agent-task-routing.json"


@dataclass(frozen=True)
class MatchResult:
    """Результат матчинга одного task type."""

    task_id: str
    score: int
    evidence: list[str]


def load_json(path: Path) -> dict[str, Any]:
    """Читает JSON-файл и возвращает словарь."""
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_path(value: str) -> str:
    """Нормализует путь к POSIX-подобному виду для простого матчинга."""
    return value.strip().replace("\\", "/").lstrip("./")


def normalize_text(value: str) -> str:
    """Нормализует текст для keyword matching."""
    return value.casefold().strip()


def unique_keep_order(items: list[str]) -> list[str]:
    """Удаляет дубли с сохранением порядка."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def read_prompt(args: argparse.Namespace) -> str:
    """Считывает prompt из аргументов."""
    if args.prompt and args.prompt_file:
        raise ValueError("Нельзя одновременно использовать --prompt и --prompt-file")
    if args.prompt_file:
        return Path(args.prompt_file).read_text(encoding="utf-8")
    return args.prompt or ""


def read_paths(args: argparse.Namespace) -> list[str]:
    """Считывает список измененных путей из аргументов."""
    paths: list[str] = []
    if args.path:
        paths.extend(args.path)
    if args.paths_file:
        raw_lines = Path(args.paths_file).read_text(encoding="utf-8").splitlines()
        paths.extend(line for line in raw_lines if line.strip())
    return [normalize_path(item) for item in paths if item.strip()]


def match_keywords(text: str, keywords: list[str]) -> list[str]:
    """Возвращает список совпавших keyword-ов."""
    matched: list[str] = []
    for keyword in keywords:
        normalized = normalize_text(keyword)
        if normalized and normalized in text:
            matched.append(keyword)
    return matched


def match_path_prefixes(paths: list[str], prefixes: list[str]) -> list[str]:
    """Возвращает совпадения по префиксам путей."""
    matched: list[str] = []
    normalized_prefixes = [normalize_path(item) for item in prefixes]
    for prefix in normalized_prefixes:
        if any(path.startswith(prefix) for path in paths):
            matched.append(prefix)
    return matched


def match_file_names(paths: list[str], file_names: list[str]) -> list[str]:
    """Возвращает совпавшие имена файлов."""
    matched: list[str] = []
    actual_names = {Path(path).name for path in paths}
    for file_name in file_names:
        if file_name in actual_names:
            matched.append(file_name)
    return matched


def paths_match_allowlist(paths: list[str], allowlist: list[str]) -> bool:
    """Проверяет, что все пути попадают в разрешенный список префиксов или имен."""
    if not paths:
        return False
    normalized_allowlist = [normalize_path(item) for item in allowlist]
    for path in paths:
        if any(path == item or path.startswith(item) for item in normalized_allowlist):
            continue
        return False
    return True


def is_excluded(task_cfg: dict[str, Any], prompt_text: str, paths: list[str]) -> bool:
    """Проверяет exclude-условия для task type."""
    exclude = task_cfg.get("exclude") or {}
    if not exclude:
        return False

    prompt_keywords = exclude.get("prompt_keywords_any") or []
    path_prefixes = exclude.get("path_prefixes_any") or []
    file_names = exclude.get("file_names_any") or []

    return bool(
        match_keywords(prompt_text, prompt_keywords)
        or match_path_prefixes(paths, path_prefixes)
        or match_file_names(paths, file_names)
    )


def score_task_type(task_cfg: dict[str, Any], prompt_text: str, paths: list[str]) -> MatchResult | None:
    """Считает score и evidence для одного task type."""
    if is_excluded(task_cfg, prompt_text, paths):
        return None

    task_id = task_cfg["id"]
    match_cfg = task_cfg.get("match") or {}
    evidence: list[str] = []
    score = 0

    prompt_matches = match_keywords(prompt_text, match_cfg.get("prompt_keywords_any") or [])
    if prompt_matches:
        score += len(prompt_matches)
        evidence.extend(f"prompt:{item}" for item in prompt_matches)

    prefix_matches = match_path_prefixes(paths, match_cfg.get("path_prefixes_any") or [])
    if prefix_matches:
        score += len(prefix_matches) * 3
        evidence.extend(f"path_prefix:{item}" for item in prefix_matches)

    file_matches = match_file_names(paths, match_cfg.get("file_names_any") or [])
    if file_matches:
        score += len(file_matches) * 2
        evidence.extend(f"file_name:{item}" for item in file_matches)

    heuristics = task_cfg.get("heuristics") or {}
    allowlist = heuristics.get("prefer_when_all_changed_paths_match") or []
    if allowlist and paths_match_allowlist(paths, allowlist):
        score += 3
        evidence.append("heuristic:all_changed_paths_match")

    if score <= 0:
        return None
    return MatchResult(task_id=task_id, score=score, evidence=evidence)


def apply_tie_break_rules(
    candidates: list[MatchResult],
    classifier: dict[str, Any],
) -> list[MatchResult]:
    """Применяет tie-break rules к списку совпавших task type."""
    by_id = {item.task_id: item for item in candidates}
    for rule in classifier.get("tie_break_rules") or []:
        overlap = rule.get("when_ids_overlap") or []
        if len(overlap) < 2:
            continue
        if not all(task_id in by_id for task_id in overlap):
            continue
        preferred_id = rule.get("prefer")
        if preferred_id not in by_id:
            continue
        preferred = by_id[preferred_id]
        max_score = max(by_id[item].score for item in overlap)
        if preferred.score < max_score:
            by_id[preferred_id] = MatchResult(
                task_id=preferred.task_id,
                score=max_score + 1,
                evidence=preferred.evidence + [f"tie_break:{rule.get('reason', 'rule_applied')}"],
            )
    return list(by_id.values())


def precedence_index(task_id: str, classifier: dict[str, Any]) -> int:
    """Возвращает индекс precedence, меньший = выше приоритет."""
    precedence = classifier.get("precedence") or []
    try:
        return precedence.index(task_id)
    except ValueError:
        return len(precedence) + 100


def select_task_type(
    classifier: dict[str, Any],
    prompt: str,
    paths: list[str],
) -> tuple[str, list[MatchResult]]:
    """Классифицирует задачу и возвращает выбранный task type."""
    prompt_text = normalize_text(prompt)
    candidates: list[MatchResult] = []
    for task_cfg in classifier.get("task_types") or []:
        result = score_task_type(task_cfg, prompt_text, paths)
        if result is not None:
            candidates.append(result)

    candidates = apply_tie_break_rules(candidates, classifier)
    if not candidates:
        return classifier["default_task_type"], []

    candidates.sort(
        key=lambda item: (-item.score, precedence_index(item.task_id, classifier), item.task_id)
    )
    return candidates[0].task_id, candidates


def build_context_pack(
    routing: dict[str, Any],
    task_id: str,
) -> dict[str, list[str]]:
    """Собирает context pack для выбранного task type."""
    base = routing["base_context_pack"]
    task_cfg = next(item for item in routing["task_types"] if item["id"] == task_id)

    agents = unique_keep_order(base.get("agents", []) + task_cfg.get("read_agents", []))
    docs = unique_keep_order(base.get("docs", []) + task_cfg.get("read_docs", []))
    code = unique_keep_order(task_cfg.get("read_code", []))
    tests = unique_keep_order(task_cfg.get("check_tests", []))
    notes = unique_keep_order(base.get("notes", []) + task_cfg.get("notes", []))

    return {
        "agents": agents,
        "docs": docs,
        "code": code,
        "tests": tests,
        "notes": notes,
    }


def collect_subsystem_tags(paths: list[str]) -> list[str]:
    """Грубо классифицирует измененные пути по подсистемам."""
    tags: list[str] = []
    for path in paths:
        if path.startswith("src/bot/"):
            tags.append("bot")
        if path.startswith("src/handlers/"):
            tags.append("handlers")
        if path.startswith("src/middlewares/"):
            tags.append("middlewares")
        if path.startswith("deploy/") or path.startswith(".github/workflows/"):
            tags.append("infra")
        if path.startswith("test/"):
            tags.append("tests")
        if path == "AGENTS.md" or path == "ARCHITECTURE.md" or path.startswith("docs/"):
            tags.append("docs")
    return unique_keep_order(tags)


def detect_escalation(
    classifier: dict[str, Any],
    selected_task_id: str,
    prompt: str,
    paths: list[str],
    candidates: list[MatchResult],
) -> tuple[bool, list[str]]:
    """Определяет, нужен ли escalation."""
    reasons: list[str] = []
    prompt_text = normalize_text(prompt)

    if selected_task_id == classifier.get("manual_review_task_type"):
        reasons.append("selected_task_type_requires_manual_review")

    high_risk_keywords = classifier.get("global_signals", {}).get("high_risk_keywords", [])
    if match_keywords(prompt_text, high_risk_keywords):
        reasons.append("prompt_contains_high_risk_keywords")

    subsystem_tags = collect_subsystem_tags(paths)
    if len([tag for tag in subsystem_tags if tag != "docs"]) >= 3:
        reasons.append("changed_paths_span_multiple_subsystems")

    if len(candidates) >= 2:
        top_two = sorted(candidates, key=lambda item: item.score, reverse=True)[:2]
        if len(top_two) == 2 and top_two[0].score - top_two[1].score <= 1:
            reasons.append("multiple_task_types_match_with_similar_confidence")

    irreversible_keywords = ["push", "release", "merge", "tag", "deploy"]
    if match_keywords(prompt_text, irreversible_keywords):
        reasons.append("prompt_requests_irreversible_action")

    return bool(reasons), unique_keep_order(reasons)


def build_output(
    classifier: dict[str, Any],
    routing: dict[str, Any],
    prompt: str,
    paths: list[str],
) -> dict[str, Any]:
    """Собирает итоговый JSON-результат."""
    selected_task_id, candidates = select_task_type(classifier, prompt, paths)
    context_pack = build_context_pack(routing, selected_task_id)
    needs_escalation, escalation_reasons = detect_escalation(
        classifier=classifier,
        selected_task_id=selected_task_id,
        prompt=prompt,
        paths=paths,
        candidates=candidates,
    )

    task_cfg = next(item for item in routing["task_types"] if item["id"] == selected_task_id)
    return {
        "task_type": {
            "id": selected_task_id,
            "label": task_cfg["label"],
        },
        "matched_task_types": [
            {
                "id": item.task_id,
                "score": item.score,
                "evidence": item.evidence,
            }
            for item in sorted(candidates, key=lambda result: (-result.score, result.task_id))
        ],
        "changed_paths": paths,
        "context_pack": context_pack,
        "escalation": {
            "needed": needs_escalation,
            "reasons": escalation_reasons,
        },
    }


def parse_args() -> argparse.Namespace:
    """Парсит аргументы CLI."""
    parser = argparse.ArgumentParser(
        description="Классификация задачи и сбор context pack для agent-first orchestration.",
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
    result = build_output(classifier=classifier, routing=routing, prompt=prompt, paths=paths)

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
